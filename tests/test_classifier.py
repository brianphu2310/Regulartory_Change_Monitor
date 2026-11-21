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


def test_real_treasury_titles_are_tagged():
    # titles fetched from treasury.gov.au/consultation on 20 Nov 2026
    assert "Tax" in classify("Crypto asset tax transparency - draft legislation", "", D)["topics"]
    assert "Tax" in classify("Global and domestic minimum tax – amending legislation tranche 4", "", D)["topics"]
    assert "Privacy & Data" in classify("Consumer Data Right FAPI 2.0 alignment – draft standards", "", D)["topics"]
    assert classify("Reforms to the bankruptcy system", "", D)["topics"] == "Other"


def test_keywords_match_whole_words_and_skip_non_firm_notices():
    assert classify("Veterans' Entitlements (Income Stream) Determination 2026", "", D)["topics"] == "Other"
    assert classify("Basic guide to the new strata scheme rules", "", D)["topics"] == "Property"   # not Tax via "bas"
    assert "Payroll" in classify("Be payroll tax ready – pay on time", "", D)["topics"]
    assert classify("Foundation to boost Indigenous legal practitioners", "", D)["topics"] == "Other"


def test_card_titles_are_cleaned():
    from bs4 import BeautifulSoup
    from monitor.fetch import clean_title
    a = BeautifulSoup('<a href="/x">announcement Preparing for land tax in 2027 16 November 2026 Revenue NSW will start '
                      'issuing land tax assessment notices.</a>', "html.parser").a
    assert clean_title(a) == "Preparing for land tax in 2027"


def test_publication_date_is_not_a_deadline():
    d = date(2026, 11, 16)
    assert extract_deadline("Preparing for land tax 16 November 2026. Notices issue on 18 January 2027.", d) == date(2027, 1, 18)
    assert extract_deadline("Revenue NSW update 16 November 2026", d) is None
