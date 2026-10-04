from datetime import date

import pandas as pd
import pytest

from classifier import classify, extract_deadline

D = date(2026, 1, 1)


def test_aml_item_is_high_impact_with_deadline_and_action():
    r = classify("AUSTRAC Tranche 2 guidance for law firms",
                 "Reporting entities must enrol by 1 July 2026. Penalties apply.", D)
    assert r["topics"] == "AML/CTF"
    assert r["impact"] == "High"
    assert r["audiences"] == "Law firms, Reporting entities"
    assert r["action_req"] == 1
    assert r["deadline"] == "2026-07-01"


def test_irrelevant_item_falls_back_to_other_low_no_action():
    r = classify("Office closed", "Nothing relevant.", D)
    assert r == {"topics": "Other", "impact": "Low", "audiences": "General", "action_req": 0, "deadline": None}


def test_multiple_topics_are_all_tagged():
    r = classify("Super guarantee and payroll update", "Employers must update payroll settings.", D)
    assert "Superannuation" in r["topics"] and "Payroll" in r["topics"]


def test_deadline_is_earliest_future_date_and_ignores_past_and_invalid():
    text = "Earlier 5 March 2025, due 30 June 2026 and again 1 July 2026. Also 31 February 2026."
    assert extract_deadline(text, D) == date(2026, 6, 30)


def test_no_deadline_when_no_date():
    assert extract_deadline("no dates here", D) is None


@pytest.mark.parametrize("title,summary,impact", [
    ("New obligation commences", "Mandatory amendment to the Act.", "High"),
    ("Draft guidance for consultation", "Review of changes.", "Medium"),
    ("Hello", "World", "Low"),
])
def test_impact_levels(title, summary, impact):
    assert classify(title, summary, D)["impact"] == impact


def test_committed_export_is_consistent():
    """The committed star-schema CSVs reference only ids that exist in the fact table."""
    ch = pd.read_csv("bi_export/changes.csv")
    assert ch["id"].is_unique and len(ch) > 100
    assert set(ch["data_type"]) == {"Sample"}  # everything is labelled synthetic
    for f, col in [("change_topics", "topic"), ("change_audiences", "audience"), ("change_departments", "department")]:
        t = pd.read_csv(f"bi_export/{f}.csv")
        assert set(t["id"]) <= set(ch["id"]), f
        assert t[col].notna().all(), f
    assert ch["impact"].isin(["High", "Medium", "Low"]).all()
