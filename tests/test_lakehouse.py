"""The lakehouse SQL (written for Databricks) run on the local DuckDB engine: load, history, idempotency, quality gate."""
import shutil

import pandas as pd
import pytest
import sqlglot

from lakehouse import run as L

LIVE = L.ROOT / "data" / "live"


def _copy(tmp_path, name="run1"):
    d = tmp_path / name
    shutil.copytree(LIVE, d)
    return d


def _eng(tmp_path):
    return L.LocalEngine(tmp_path / "db" / "workspace.duckdb")


def test_statement_splitter_skips_comments_and_marks_remote_only():
    sts = L.statements("-- note; with a semicolon\nSELECT 1;\n-- @remote\nCREATE VOLUME x;\nSELECT\n  2;")
    assert sts == [("SELECT 1", False), ("CREATE VOLUME x", True), ("SELECT\n  2", False)]


@pytest.mark.parametrize("path", sorted(L.SQL_DIR.glob("*.sql")), ids=lambda p: p.name)
def test_every_statement_is_valid_databricks_sql(path):
    eng = L.DatabricksEngine.__new__(L.DatabricksEngine)
    eng.catalog = "workspace"
    for sql, _ in L.statements(path.read_text()):
        sqlglot.parse_one(eng.render(sql, "2026-11-23"), read="databricks")


def test_load_matches_the_csv_files(tmp_path):
    src = _copy(tmp_path)
    eng = _eng(tmp_path)
    res = eng.load(src, "2026-11-23")
    assert res["quality"][res["quality"]["blocking"]]["passed"].all()
    dash = pd.read_csv(src / "dashboard_changes.csv")
    gold = eng.query("SELECT * FROM workspace.rcm_gold.dashboard_changes")
    assert len(gold) == len(dash) and gold["total_one_off_cost"].sum() == pytest.approx(dash["total_one_off_cost"].sum())
    assert len(eng.query("SELECT * FROM workspace.rcm_gold.changes")) == len(pd.read_csv(src / "changes.csv"))
    snap = res["weekly_snapshot"].iloc[-1]
    assert snap["changes_on_file"] == len(dash)
    assert snap["needs_action"] == (dash["work_status"] == "Outstanding").sum()


def test_rerunning_a_date_replaces_instead_of_duplicating(tmp_path):
    src = _copy(tmp_path)
    eng = _eng(tmp_path)
    eng.load(src, "2026-11-23")
    res = eng.load(src, "2026-11-23")
    assert len(res["weekly_snapshot"]) == 1
    assert eng.query("SELECT COUNT(*) n FROM workspace.rcm_bronze.changes")["n"][0] == len(pd.read_csv(src / "changes.csv"))
    assert eng.query("SELECT COUNT(*) n FROM workspace.rcm_silver.dashboard_history")["n"][0] == len(pd.read_csv(src / "dashboard_changes.csv"))


def test_history_keeps_first_seen_and_flags_dropped_changes(tmp_path):
    eng = _eng(tmp_path)
    first = _copy(tmp_path, "w1")
    eng.load(first, "2026-11-16")
    second = _copy(tmp_path, "w2")
    c = pd.read_csv(second / "changes.csv")
    dropped = c["id"].iloc[0]
    c.iloc[1:].to_csv(second / "changes.csv", index=False)
    d = pd.read_csv(second / "dashboard_changes.csv")
    d[d["id"] != dropped].to_csv(second / "dashboard_changes.csv", index=False)
    res = eng.load(second, "2026-11-23")
    s = eng.query("SELECT id, first_seen_run, last_seen_run, is_current FROM workspace.rcm_silver.changes")
    row = s[s["id"] == dropped].iloc[0]
    assert not row["is_current"] and str(row["last_seen_run"])[:10] == "2026-11-16"
    kept = s[s["id"] != dropped]
    assert kept["is_current"].all() and (kept["first_seen_run"].astype(str).str[:10] == "2026-11-16").all()
    assert dropped not in set(eng.query("SELECT id FROM workspace.rcm_gold.changes")["id"])
    assert list(res["weekly_snapshot"]["changes_on_file"]) == [len(c), len(c) - 1]


def test_blocking_quality_check_stops_the_load_before_silver(tmp_path):
    src = _copy(tmp_path)
    c = pd.read_csv(src / "changes.csv")
    pd.concat([c, c.iloc[:1]]).to_csv(src / "changes.csv", index=False)   # duplicate id
    eng = _eng(tmp_path)
    with pytest.raises(L.QualityError, match="id unique"):
        eng.load(src, "2026-11-23")
    assert eng.query("SELECT COUNT(*) n FROM workspace.rcm_silver.changes")["n"][0] == 0


def test_sample_backfill_ends_on_the_report_numbers():
    snap = pd.read_csv(L.ROOT / "bi_export" / "weekly_snapshot.csv")
    last = snap.iloc[-1]
    assert (last["changes_on_file"], last["needs_action"], last["past_target_date"]) == (200, 54, 27)
    assert round(last["one_off_cost"]) == 137365 and round(last["backlog_hours"]) == 473
    assert snap["run_date"].is_monotonic_increasing and len(snap) >= 40
