# Power BI report (PBIP)

`RegulatoryChangeMonitor.pbip` is the v1 report extended with two pages, **Finance impact** and **Capacity & sources**,
saved as a Power BI **project**: the model is TMDL text and the report is PBIR JSON, so every measure, relationship
and visual can be reviewed in Git. [`build_pbip.py`](build_pbip.py) generates it:

1. unpacks the v1 report pages, theme and backgrounds from `regulatory_change_monitor.pbix`;
2. rebuilds the v1 model as TMDL (tables, relationships, calculated tables and columns, measures, recovered with
   `pbixray`), now reading the CSVs from GitHub instead of a local folder;
3. adds the impact and monitor tables and their measures;
4. adds the two pages and redraws every sidebar with ten items.

## Open it (first time, about 5 minutes)

1. Get the repo: **Code > Download ZIP** and extract, or `git clone`.
2. Open `powerbi/RegulatoryChangeMonitor.pbip` in Power BI Desktop (2025 or later).
3. Press **Refresh**. When asked how to connect to `https://raw.githubusercontent.com`, choose **Anonymous**, privacy
   level **Public**.
4. Choose the data: **Transform data > Edit parameters**
   - `Dataset` = `bi_export` (synthetic year, every page populated) or `data/live` (the weekly monitor)
   - `Branch` = `main`
5. Optional: **File > Save as** `.pbix` to share a single file.

Every Monday after 07:17 Sydney the monitor commits a new run; with `Dataset = data/live`, **Refresh** loads it.

## Data source: CSV or Databricks

| Parameter | Values | Default |
|---|---|---|
| `Source` | `GitHub CSV` (the files in this repo) or `Databricks` (the lakehouse gold tables) | `GitHub CSV` |
| `Dataset` | `bi_export` (synthetic year) or `data/live` (weekly monitor); CSV mode only | `bi_export` |
| `DatabricksHost`, `DatabricksHttpPath`, `DatabricksCatalog` | from the SQL warehouse's *Connection details*; Databricks mode only | placeholders, `workspace` |

Both sources have the same table and column names, so every page works on either. Only the chosen branch of each query
is evaluated, so CSV mode never asks for Databricks credentials. Set-up: [docs/DATABRICKS.md](../docs/DATABRICKS.md).

## See it without Power BI

`python powerbi/render_preview.py` draws every page from the report's own `page.json` / `visual.json` files (positions,
fields, filters, sort, colours) and the same CSVs, with each measure re-implemented in pandas, into `preview/report.html`.
That file is the live link in the main README. `tests/test_report_preview.py` pins the headline numbers.

## Model

| Table | Source | Used by |
|---|---|---|
| `changes`, `change_topics`, `change_audiences`, `dim_date` | CSV | v1 pages |
| `open_actions`, `dim_topic`, `dim_department`, `topic_department` | DAX calculated tables | v1 pages |
| `dashboard_changes`, `change_effort`, `capacity_monthly` | CSV (impact model) | Finance impact, Capacity & sources |
| `run_log` | CSV (live runs only; empty in sample mode) | Source health |

Relationships as in v1 (`changes` to `dim_date` on published, inactive on deadline; topic and audience bridges both
ways) plus `change_effort` to `dashboard_changes`, and the department path `dim_department` → `topic_department` →
`dim_topic` → `change_topics` → `changes`, so each department page shows only the changes whose topics reach it.
Deadlines and "last 30 days" count from the date of the data (`As Of Date` = latest `as_of`), not from the day the file is opened. The v1 measure **Sample Data Note** now says whether sample or live
data is loaded.

## Design system

Same tokens as v1: slate `#46586B`, ink `#1F2933`, lime `#B6D94C`, page `#E6EAEE`; red `#C0392B` past target, amber
`#D98C00` under 14 days. Sidebar, header banner, KPI tiles and panel frames are drawn into the page backgrounds so
visuals sit on top without borders. Layout is in `NEW_PAGES` and `NAV`, colours in `TOKENS`.

## If Desktop reports an error on open

The project is generated rather than saved by Desktop, so a schema detail can differ between Desktop versions. The
message names the file and property: fix it in `build_pbip.py`, run `python powerbi/build_pbip.py`, reopen.
`tests/test_powerbi_project.py` already checks that every field used by any of the 14 pages exists in the model and
that every model column exists in the CSVs.
