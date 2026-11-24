"""The report preview reads the Power BI project itself; these tests pin the model fixes and the headline numbers."""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "powerbi" / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("build_pbip", "build_pbip.py")
P = _load("render_preview", "render_preview.py")


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    B.build()
    out = tmp_path_factory.mktemp("prev") / "report.html"
    P.Renderer("bi_export").build(out)
    return out.read_text()


def test_departments_reach_changes_through_their_topics():
    rels = {(f, t) for f, t, _, _ in B.RELATIONSHIPS}
    assert ("topic_department.department", "dim_department.department") in rels
    assert ("topic_department.topic", "dim_topic.topic") in rels
    assert ("change_topics.topic", "dim_topic.topic") in rels


def test_dates_count_from_the_data_not_the_day_the_file_is_opened():
    dax = [e for _, e, _, _ in B.V1_MEASURES if not e.startswith("COALESCE")] + [e for _, _, e in B.CALC_COLUMNS["changes"]]
    for e in dax:
        assert "TODAY ()" not in e.replace("COALESCE ( MAXX ( ALL ( dashboard_changes ), dashboard_changes[as_of] ), TODAY () )", "")


def test_every_visual_renders(html):
    assert "class=\"v unk\"" not in html
    assert html.count('class="page"') == 11


def test_headline_numbers(html):
    E = P.Engine(P.Data("bi_export"))
    _, c = E.frame("changes", [], [])
    m = E.M["changes"]
    assert (m["Total Changes"](c), m["High Impact"](c), m["Open Actions"](c), m["Overdue Actions"](c)) == (200, 69, 54, 16)
    acc = c[c["id"].isin(E.D.dept[E.D.dept["department"] == "Accounts & Trust"]["id"])]
    assert m["Total Changes"](acc) == 106          # the department pages differ from the firm total
    d = E.M["dashboard_changes"]
    assert round(d["One-off Cost"](E.D.dash)) == 137365 and d["Past Target Date"](E.D.dash) == 27
    assert re.search(r">286%<", html)               # peak month load, Oct 2026
