# Skills demonstrated

| Skill | Where to see it |
|---|---|
| Power BI: star schema with bridge tables, DAX measures, drill-through and report-page tooltips, synced slicers, conditional formatting driven by measures | `powerbi/regulatory_change_monitor.pbix`, `POWERBI_GUIDE.md` |
| Dimensional modelling (fact, date and department/topic dimensions, many-to-many bridges) | `bi_export/`, `export_for_bi.py` |
| Rule-based text classification, explainable and testable | `classifier.py`, `tests/test_classifier.py` |
| Python data generation with a fixed seed and honest labelling of synthetic data | `generate_synthetic.py`, `data_type = Sample` |
| SQLite storage and CSV export for BI tools | `db.py`, `export_for_bi.py` |
| Interactive prototyping (d3 HTML preview, Streamlit explorer) | `preview/dashboard_preview.html`, `app.py` |
| Data documentation | `docs/DATA_DICTIONARY.md` |
| Automated tests and CI | `tests/`, `.github/workflows/ci.yml` |

Not claimed: no web scraping, no live agency data, no trained model, no cloud deployment.

## v2 and v3 (impact model and live monitor)

| Skill | Where |
|---|---|
| Cost and capacity modelling (staff time × loaded rate, external spend, monthly load by role) | `impact_model.py`, `docs/IMPACT_MODEL.md` |
| Web data collection with robots.txt checks and per-source error handling | `monitor/fetch.py`, `monitor/sources.py` |
| Containerisation | `Dockerfile`, `run_local.ps1` |
| Scheduled orchestration, automated commits and issue reports | `.github/workflows/monitor.yml` |
| Power BI as code: TMDL semantic model, PBIR report, DAX, Power Query M with parameters | `powerbi/build_pbip.py` |
| System design with explicit trade-offs | `docs/ARCHITECTURE.md` |
