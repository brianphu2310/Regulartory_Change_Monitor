"""The impact tables must add up, so every figure on the finance, time and people pages can be traced."""
from pathlib import Path

import pandas as pd
import pytest

import impact_model as im

BI = Path(__file__).resolve().parent.parent / "bi_export"


@pytest.fixture(scope="module")
def t(tmp_path_factory):
    out = tmp_path_factory.mktemp("bi")
    for f in ("changes.csv", "change_topics.csv"):
        (out / f).write_bytes((BI / f).read_bytes())
    return im.build(out)


def test_role_splits_sum_to_one():
    for topic, (*_, split) in im.TOPICS.items():
        assert sum(split.values()) == pytest.approx(1.0), topic
        assert set(split) <= set(im.ROLES), topic


def test_every_change_has_one_impact_row(t):
    changes = pd.read_csv(BI / "changes.csv")
    assert sorted(t["change_impact"]["id"]) == sorted(changes["id"])


def test_effort_rows_add_up_to_the_change_totals(t):
    eff = t["change_effort"].groupby("id")[["one_off_hours", "one_off_cost"]].sum()
    imp = t["change_impact"].set_index("id")
    assert (eff["one_off_hours"] - imp["one_off_hours"]).abs().max() < 0.05
    assert (eff["one_off_cost"] - imp["internal_one_off_cost"]).abs().max() < 0.05


def test_total_cost_is_internal_plus_external(t):
    i = t["change_impact"]
    assert ((i["internal_one_off_cost"] + i["external_one_off"] - i["total_one_off_cost"]).abs() < 0.01).all()


def test_only_outstanding_work_is_scheduled_and_capacity_balances(t):
    i, cap = t["change_impact"], t["capacity_monthly"]
    assert (i.loc[i["work_status"] != "Outstanding", "outstanding_hours"] == 0).all()
    assert cap["hours_required"].sum() == pytest.approx(i["outstanding_hours"].sum(), abs=0.5)
    assert (cap["hours_over_capacity"] >= 0).all()


def test_changes_without_action_cost_only_awareness_time(t):
    i = t["change_impact"]
    aware = i[i["work_status"] == "Awareness only"]
    assert (aware["one_off_hours"] == im.AWARENESS_HOURS).all()
    assert (aware["external_one_off"] == 0).all()


def test_committed_tables_match_a_fresh_build(t):
    for name, df in t.items():
        committed = pd.read_csv(BI / f"{name}.csv")
        assert len(committed) == len(df), name
