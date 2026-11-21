"""The generated Power BI project must be internally consistent: every field a visual uses exists in the model,
every table reads a column the CSV actually has, and every JSON file parses."""
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build_pbip", ROOT / "powerbi" / "live" / "build_pbip.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


@pytest.fixture(scope="module", autouse=True)
def built():
    B.build()


def _fields(obj):
    if isinstance(obj, dict):
        for kind in ("Column", "Measure"):
            if kind in obj and isinstance(obj[kind], dict) and "Property" in obj[kind]:
                ent = obj[kind]["Expression"]["SourceRef"].get("Entity")
                if ent:
                    yield kind, ent, obj[kind]["Property"]
        for v in obj.values():
            yield from _fields(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _fields(v)


def test_every_json_file_parses():
    files = list((ROOT / "powerbi" / "live").rglob("*.json")) + list((ROOT / "powerbi" / "live").rglob("*.pbi*"))
    assert len(files) > 20
    for f in files:
        if f.suffix in (".json", ".pbir", ".pbism", ".pbip"):
            json.loads(f.read_text())


def test_visual_fields_exist_in_the_model():
    cols = {(t, c) for t, (_, _, cs) in B.TABLES.items() for c, _ in cs}
    measures = {(t, m) for t, ms in B.MEASURES.items() for m, _, _ in ms}
    used = 0
    for f in B.REPORT.rglob("visual.json"):
        for kind, ent, prop in _fields(json.loads(f.read_text())):
            used += 1
            assert (ent, prop) in (cols if kind == "Column" else measures), f"{f.parent.name}: {kind} {ent}.{prop}"
    assert used > 40


@pytest.mark.parametrize("table", ["dashboard_changes", "change_effort", "capacity_monthly"])
def test_model_columns_match_the_csv(table):
    file, _, cols = B.TABLES[table]
    assert [c for c, _ in cols] == list(pd.read_csv(ROOT / "bi_export" / file, nrows=1).columns)


def test_run_log_columns_match_what_the_monitor_writes():
    from monitor import run
    assert [c for c, _ in B.TABLES["run_log"][2]] == ["run_at", "agency", "feed", "status", "items"]
    assert "run_at" in Path(run.__file__).read_text()


def test_every_page_has_navigation_and_a_background():
    pages = json.loads((B.REPORT / "definition" / "pages" / "pages.json").read_text())["pageOrder"]
    assert len(pages) == len(B.PAGES)
    for pid in pages:
        page = json.loads((B.REPORT / "definition" / "pages" / pid / "page.json").read_text())
        bg = page["objects"]["background"][0]["properties"]["image"]["image"]["url"]["expr"]["ResourcePackageItem"]["ItemName"]
        assert (B.REPORT / "StaticResources" / "RegisteredResources" / bg).exists()
        navs = [p for p in (B.REPORT / "definition" / "pages" / pid / "visuals").iterdir() if p.name.startswith("nav")]
        assert len(navs) == len(B.PAGES)
