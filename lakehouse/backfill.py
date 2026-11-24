"""Replay the synthetic sample year through the lakehouse, one weekly run at a time, to build its history.

    python -m lakehouse.backfill            # writes bi_export/weekly_snapshot.csv and bi_export/quality_checks.csv

The live data has history from its first Databricks load onward. The sample (bi_export) is a single snapshot, so to give
the report's Weekly trend page something to show in sample mode, this replays it: for every Monday it keeps the changes
published by then, costs them with impact_model.build(as_of=that Monday) and loads the result with the same SQL as the
weekly job (DuckDB engine). One stated simplification: a change whose final status is Actioned counts as actioned only
from 30 days after it was published; before that it is still open work.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pandas as pd

import impact_model
from lakehouse.run import ROOT, LocalEngine, write_back

SAMPLE = ROOT / "bi_export"
ACTION_LAG_DAYS = 30


def week_folder(tmp: Path, week: pd.Timestamp, changes: pd.DataFrame, topics: pd.DataFrame,
                audiences: pd.DataFrame, dim_date: pd.DataFrame, final: bool = False) -> Path:
    d = tmp / str(week.date())
    d.mkdir(parents=True)
    c = changes[changes["published"] <= week].copy()
    if not final:   # the last run is the sample as it stands, so the trend ends on the report's own numbers
        late = (c["status"] == "Actioned") & (c["published"] > week - pd.Timedelta(days=ACTION_LAG_DAYS))
        c.loc[late, "status"] = "Reviewed"
    c["first_seen"] = c["published"]
    c["feed"] = ""
    for col in ("published", "deadline", "first_seen"):
        c[col] = pd.to_datetime(c[col]).dt.date
    c.to_csv(d / "changes.csv", index=False)
    topics[topics["id"].isin(c["id"])].to_csv(d / "change_topics.csv", index=False)
    audiences[audiences["id"].isin(c["id"])].to_csv(d / "change_audiences.csv", index=False)
    dim_date.to_csv(d / "dim_date.csv", index=False)
    impact_model.build(d, as_of=week)
    pd.DataFrame(columns=["run_at", "agency", "feed", "status", "items"]).to_csv(d / "run_log.csv", index=False)
    return d


def main() -> None:
    changes = pd.read_csv(SAMPLE / "changes.csv", parse_dates=["published", "deadline"])
    topics = pd.read_csv(SAMPLE / "change_topics.csv")
    audiences = pd.read_csv(SAMPLE / "change_audiences.csv")
    dim_date = pd.read_csv(SAMPLE / "dim_date.csv")
    as_of = pd.to_datetime(pd.read_csv(SAMPLE / "dashboard_changes.csv")["as_of"]).max()
    start = changes["published"].min() + pd.Timedelta(days=28)
    weeks = list(pd.date_range(start - pd.Timedelta(days=start.weekday()), as_of, freq="W-MON"))
    if weeks[-1] != as_of:
        weeks.append(as_of)
    tmp = Path(tempfile.mkdtemp())
    try:
        eng = LocalEngine(tmp / "workspace.duckdb")
        for w in weeks:
            eng.load(week_folder(tmp, w, changes, topics, audiences, dim_date, final=w == weeks[-1]), str(w.date()))
        result = {"weekly_snapshot": eng.query("SELECT * FROM workspace.rcm_gold.weekly_snapshot ORDER BY run_date"),
                  "quality_checks": eng.query("SELECT * FROM workspace.rcm_silver.quality_checks ORDER BY run_date, check_name")}
        write_back(SAMPLE, result)
        print(f"{len(weeks)} weekly runs replayed -> bi_export/weekly_snapshot.csv")
        print(result["weekly_snapshot"].tail(5).to_string(index=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
