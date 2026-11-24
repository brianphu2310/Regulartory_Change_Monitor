"""Build the Power BI project (PBIP) for the Regulatory Change Monitor from code.

    python powerbi/build_pbip.py

Starts from the v1 report (powerbi/regulatory_change_monitor.pbix: its PBIR pages, theme and backgrounds are reused
as they are) and adds:

  * a TMDL semantic model rebuilt from the v1 model (same tables, relationships, calculated tables and measures,
    recovered with pbixray), now reading the CSVs from GitHub with two parameters, Branch and Dataset
    (bi_export = synthetic year, data/live = the weekly monitor);
  * the v2/v3 tables: dashboard_changes, change_effort, capacity_monthly, run_log;
  * two new pages in the same design, Finance impact and Capacity & sources, with the sidebar of every page redrawn
    to include them.

Open powerbi/RegulatoryChangeMonitor.pbip in Power BI Desktop and press Refresh.
"""
from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
NAME = "RegulatoryChangeMonitor"
PBIX = HERE / "regulatory_change_monitor.pbix"
REPORT = HERE / f"{NAME}.Report"
MODEL = HERE / f"{NAME}.SemanticModel"
REPO = "brianphu2310/Regulartory_Change_Monitor"

TOKENS = {
    "page": "#E6EAEE", "ink": "#1F2933", "slate": "#46586B", "slate_mid": "#3B4B5C", "slate_dark": "#24303B",
    "night": "#151D25", "lime": "#B6D94C", "lime_dark": "#5F7A1A", "panel": "#F6F8F4", "muted": "#C3CCD6",
    "amber": "#D98C00", "red": "#C0392B", "white": "#FFFFFF",
}
W, H = 1920, 1080
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
VC_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.13.0/schema.json"

# ----------------------------------------------------------------------------------------------- layout (pixels)
SIDEBAR = (18, 18, 346, 1062)
CONTENT_X0, CONTENT_X1 = 372, 1884
HEADER = (CONTENT_X0, 24, CONTENT_X1, 96)
KPI_Y = (116, 236)
NEW_PAGES = [
    {"id": "p_finance000000000001", "name": "Finance impact", "title": "FINANCE IMPACT",
     "subtitle": "What changed, what it costs, and who does the work",
     "kpis": ["NEW THIS WEEK", "NEEDS ACTION", "PAST TARGET DATE", "ONE-OFF COST", "BACKLOG HOURS"],
     "panels": {"table": ((372, 316, 1260, 1056), "What changed and what it costs"),
                "cost": ((1280, 316, 1884, 676), "Cost by department: staff time vs external"),
                "people": ((1280, 696, 1884, 1056), "Who does the work: hours needed vs available")}},
    {"id": "p_capacity00000000001", "name": "Capacity & sources", "title": "CAPACITY & SOURCES",
     "subtitle": "Can the team absorb the backlog, and did every source answer this run?",
     "kpis": ["PEAK MONTH LOAD", "HOURS OVER CAPACITY", "FTE GAP (MONTHS)", "ONGOING COST / YR", "SOURCES OK (LIVE)"],
     "panels": {"heat": ((372, 316, 1260, 676), "Capacity load by role and month"),
                "roles": ((1280, 316, 1884, 676), "Outstanding hours by role"),
                "due": ((372, 696, 1000, 1056), "Backlog by target month"),
                "log": ((1020, 696, 1884, 1056), "Source health: latest weekly run (live)")}},
    {"id": "p_trend00000000000001", "name": "Weekly trend", "title": "WEEKLY TREND",
     "subtitle": "Every weekly run kept in the Databricks lakehouse: is the backlog shrinking?",
     "kpis": ["WEEKLY RUNS", "CHANGES ON FILE", "BACKLOG HOURS", "BACKLOG vs 4 WEEKS AGO", "QUALITY CHECKS PASSED"],
     "panels": {"backlog": ((372, 316, 1260, 676), "Open actions (columns) and backlog hours (line), week by week"),
                "volume": ((1280, 316, 1884, 676), "New changes each week and changes on file"),
                "late": ((372, 696, 1260, 1056), "Changes past their target date"),
                "quality": ((1280, 696, 1884, 1056), "Data quality checks: latest load")}},
]
# sidebar order: v1 pages with the two new pages before Action tracker and About
NAV = [("p7ov0000000000000001", "Overview", "◎"), ("p7d00000000000000001", "Accounts & Trust", "▣"),
       ("p7d10000000000000001", "Compliance & AML", "⚑"), ("p7d20000000000000001", "HR & Payroll", "☺"),
       ("p7d30000000000000001", "Property", "⌂"), ("p7d40000000000000001", "Privacy & IT", "◈"),
       ("p_finance000000000001", "Finance impact", "$"), ("p_capacity00000000001", "Capacity & sources", "▦"),
       ("p_trend00000000000001", "Weekly trend", "↗"),
       ("p7tk0000000000000001", "Action tracker", "✓"), ("p7ab0000000000000001", "About", "i")]
NAV_Y0, NAV_STEP = 184, 62


# ------------------------------------------------------------------------------------------- background images
def _chamfer(box, c=18):
    x0, y0, x1, y1 = box
    return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]


def _gradient(size, top, bottom):
    g = Image.new("RGB", size, top)
    d = ImageDraw.Draw(g)
    t, b = Image.new("RGB", (1, 1), top).getpixel((0, 0)), Image.new("RGB", (1, 1), bottom).getpixel((0, 0))
    for y in range(size[1]):
        f = y / max(size[1] - 1, 1)
        d.line([(0, y), (size[0], y)], fill=tuple(int(t[i] + (b[i] - t[i]) * f) for i in range(3)))
    return g


def _shape(img, poly, fill_img=None, fill=None, outline=None, shadow=True):
    if shadow:
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).polygon([(x + 4, y + 6) for x, y in poly], fill=90)
        img.paste((150, 158, 168), mask=sh.filter(ImageFilter.GaussianBlur(7)))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    if fill_img is not None:
        x0, y0 = min(p[0] for p in poly), min(p[1] for p in poly)
        layer = Image.new("RGB", (W, H))
        layer.paste(fill_img, (x0, y0))
        img.paste(layer, mask=mask)
    else:
        img.paste(fill, mask=mask)
    if outline:
        ImageDraw.Draw(img).line(poly + [poly[0]], fill=outline, width=2)


def sidebar(img: Image.Image, active: str | None) -> None:
    """Draw the sidebar (logo, name, the ten navigation items) with `active` highlighted. Clears the old one first."""
    T = TOKENS
    d = ImageDraw.Draw(img)
    f = lambda s, b=False: ImageFont.truetype(FONT_B if b else FONT, s)
    d.rectangle((0, 0, 362, H), fill=T["page"])
    sx0, sy0, sx1, sy1 = SIDEBAR
    _shape(img, _chamfer(SIDEBAR, 22), fill_img=_gradient((sx1 - sx0 + 1, sy1 - sy0 + 1), T["slate"], T["night"]))
    d.ellipse((62, 56, 138, 132), outline=T["lime"], width=4)
    d.ellipse((70, 64, 130, 124), fill=T["ink"])
    d.text((100, 94), "BP", font=f(30, True), fill=T["lime"], anchor="mm")
    d.text((160, 80), "Brian Phu", font=f(22, True), fill=T["white"], anchor="lm")
    d.text((160, 106), "DATA ANALYST", font=f(13, True), fill=T["lime"], anchor="lm")
    d.line((46, 160, 318, 160), fill=T["lime"], width=2)
    for i, (pid, label, icon) in enumerate(NAV):
        y, on = NAV_Y0 + i * NAV_STEP, pid == active
        if on:
            _shape(img, _chamfer((30, y, 330, y + 56), 10), fill=T["lime"], shadow=False)
        d.text((62, y + 28), icon, font=f(22, True), fill=T["ink"] if on else T["lime"], anchor="mm")
        d.text((96, y + 28), label, font=f(20, on), fill=T["ink"] if on else T["white"], anchor="lm")
    d.text((182, 1000), "SAMPLE OR LIVE DATA", font=f(13, True), fill=T["lime"], anchor="mm")
    d.text((182, 1022), "NOT LEGAL ADVICE", font=f(13, True), fill=T["muted"], anchor="mm")


def background(page: dict, path: Path) -> None:
    T = TOKENS
    img = Image.new("RGB", (W, H), T["page"])
    d = ImageDraw.Draw(img)
    f = lambda s, b=False: ImageFont.truetype(FONT_B if b else FONT, s)

    sidebar(img, page["id"])

    # header banner with the lime stripe
    hx0, hy0, hx1, hy1 = HEADER
    banner = [(hx0, hy0), (hx1 - 36, hy0), (hx1, (hy0 + hy1) // 2), (hx1 - 36, hy1), (hx0, hy1)]
    _shape(img, banner, fill_img=_gradient((hx1 - hx0 + 1, hy1 - hy0 + 1), T["slate_dark"], T["slate_mid"]))
    d.polygon([(1478, hy0), (1532, hy0), (1504, hy1), (1450, hy1)], fill=T["lime"])
    d.polygon([(1550, hy0), (1574, hy0), (1546, hy1), (1522, hy1)], fill=T["slate"])
    d.text((hx0 + 34, hy0 + 26), page["title"], font=f(30, True), fill=T["white"], anchor="lm")
    d.text((hx0 + 36, hy0 + 56), page["subtitle"], font=f(15), fill=T["muted"], anchor="lm")

    # KPI tiles
    n = len(page["kpis"])
    if n:
        gap = 20
        tw = (CONTENT_X1 - CONTENT_X0 - gap * (n - 1)) // n
        for i, label in enumerate(page["kpis"]):
            x0 = CONTENT_X0 + i * (tw + gap)
            box = (x0, KPI_Y[0], x0 + tw, KPI_Y[1])
            _shape(img, _chamfer(box, 18), fill_img=_gradient((tw + 1, KPI_Y[1] - KPI_Y[0] + 1), T["slate"], T["slate_dark"]),
                   outline=T["lime"])
            d.text((x0 + tw // 2, KPI_Y[0] + 24), label, font=f(15, True), fill="#E4E9EE", anchor="mm")

    # panels: dark header strip, lime rule, light body
    for (x0, y0, x1, y1), title in page["panels"].values():
        _shape(img, _chamfer((x0, y0, x1, y1), 16), fill_img=_gradient((x1 - x0 + 1, y1 - y0 + 1), "#F7F9F5", "#EEF1EC"))
        if title:
            strip = [(x0 + 16, y0), (x1 - 16, y0), (x1, y0 + 16), (x1, y0 + 44), (x0, y0 + 44), (x0, y0 + 16)]
            _shape(img, strip, fill_img=_gradient((x1 - x0 + 1, 45), T["slate_dark"], T["slate_mid"]), shadow=False)
            d.line((x0, y0 + 45, x1, y0 + 45), fill=T["lime"], width=3)
            d.text(((x0 + x1) // 2, y0 + 23), title, font=f(17, True), fill=T["white"], anchor="mm")
    img.save(path, optimize=True)


# ------------------------------------------------------------------------------------------------ semantic model
LIVE_ONLY = {"run_log"}   # real in both modes: the run log only exists in data/live


def _source(table: str, file: str, types: list[tuple[str, str]], optional: bool = False) -> str:
    """M for one table. Source = "GitHub CSV" reads the CSV from the repo (Dataset folder); Source = "Databricks" reads the
    same table from the lakehouse gold schema. Only the chosen branch is evaluated, so CSV mode never asks for
    Databricks credentials."""
    type_list = ", ".join(f'{{"{c}", {t}}}' for c, t in types)
    names = "{" + ", ".join(f'"{c}"' for c, _ in types) + "}"
    folder = '"data/live"' if table in LIVE_ONLY else "Dataset"
    fetch = (f'Csv.Document(Web.Contents("https://raw.githubusercontent.com", [RelativePath = "{REPO}/" & Branch & "/" & {folder} & "/{file}"]), '
             f'[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv])')
    csv = f"Table.PromoteHeaders({fetch}, [PromoteAllScalars = true])"
    if optional:   # not there yet (no run, no lakehouse load): an empty table keeps the report working
        empty = "#table(type table [" + ", ".join(f"{c} = text" for c, _ in types) + "], {})"
        csv = f"try Table.Buffer({csv}) otherwise {empty}"
    lake = (f'Databricks.Catalogs(DatabricksHost, DatabricksHttpPath, [Catalog = null, Database = null, EnableAutomaticProxyDiscovery = null])'
            f'{{[Name = DatabricksCatalog, Kind = "Database"]}}[Data]{{[Name = "rcm_gold", Kind = "Schema"]}}[Data]'
            f'{{[Name = "{table}", Kind = "Table"]}}[Data]')
    body = (f"    Raw = if Source = \"Databricks\" then {lake}\n          else {csv},\n"
            f"    Picked = Table.SelectColumns(Raw, {names}, MissingField.UseNull),\n"
            f"    Typed = Table.TransformColumnTypes(Picked, {{{type_list}}}, \"en-AU\")")
    return f"let\n{body}\nin\n    Typed"


TYPES = {"text": ("string", "type text"), "int": ("int64", "Int64.Type"), "num": ("double", "type number"),
         "date": ("dateTime", "type date"), "dt": ("dateTime", "type datetimezone")}
TABLES = {
    # v1 star schema (same columns and types as the v1 model)
    "changes": ("changes.csv", False, [
        ("id", "text"), ("published", "date"), ("source", "text"), ("title", "text"), ("summary", "text"), ("link", "text"),
        ("impact", "text"), ("action_req", "int"), ("deadline", "date"), ("status", "text"), ("impact_sort", "int"),
        ("data_type", "text"), ("topics", "text"), ("audiences", "text")]),
    "change_topics": ("change_topics.csv", False, [("id", "text"), ("topic", "text")]),
    "change_audiences": ("change_audiences.csv", False, [("id", "text"), ("audience", "text")]),
    "dim_date": ("dim_date.csv", False, [
        ("date", "date"), ("year", "int"), ("month_num", "int"), ("month_name", "text"), ("year_month", "text"),
        ("month_start", "date"), ("week_start", "date")]),
    # v2 / v3
    "dashboard_changes": ("dashboard_changes.csv", False, [
        ("id", "text"), ("source", "text"), ("title", "text"), ("link", "text"), ("impact", "text"), ("impact_sort", "int"),
        ("topics", "text"), ("status", "text"), ("action_req", "int"), ("published", "date"), ("deadline", "date"),
        ("one_off_hours", "num"), ("ongoing_hours_yr", "num"), ("external_one_off", "num"), ("external_ongoing_yr", "num"),
        ("internal_one_off_cost", "num"), ("internal_ongoing_cost_yr", "num"), ("total_one_off_cost", "num"),
        ("total_ongoing_cost_yr", "num"), ("target_date", "date"), ("lead_time_days", "int"), ("days_left", "int"),
        ("work_status", "text"), ("outstanding_hours", "num"), ("at_risk", "int"), ("as_of", "date"), ("first_seen", "date"),
        ("lead_role", "text"), ("lead_department", "text")]),
    "change_effort": ("change_effort.csv", False, [
        ("id", "text"), ("role", "text"), ("one_off_hours", "num"), ("ongoing_hours_yr", "num"), ("one_off_cost", "num"),
        ("ongoing_cost_yr", "num"), ("department", "text"), ("hourly_cost", "num")]),
    "capacity_monthly": ("capacity_monthly.csv", False, [
        ("month_start", "date"), ("role", "text"), ("hours_required", "num"), ("hours_available", "num"),
        ("load_pct", "num"), ("hours_over_capacity", "num")]),
    "run_log": ("run_log.csv", True, [
        ("run_at", "dt"), ("agency", "text"), ("feed", "text"), ("status", "text"), ("items", "int")]),
    # lakehouse (v4): written by lakehouse/run.py after each load, and by lakehouse/backfill.py for the sample
    "weekly_snapshot": ("weekly_snapshot.csv", True, [
        ("run_date", "date"), ("changes_on_file", "int"), ("new_this_run", "int"), ("high_impact", "int"),
        ("needs_action", "int"), ("past_target_date", "int"), ("one_off_cost", "num"), ("ongoing_cost_yr", "num"),
        ("backlog_hours", "num"), ("peak_month_load", "num"), ("sources_checked", "int"), ("sources_ok", "int")]),
    "quality_checks": ("quality_checks.csv", True, [
        ("run_date", "date"), ("check_name", "text"), ("blocking", "text"), ("failed_rows", "int"), ("passed", "text")]),
}
V1_MEASURES = [
    ("As Of Date", "COALESCE ( MAXX ( ALL ( dashboard_changes ), dashboard_changes[as_of] ), TODAY () )", "d mmm yyyy", "Labels"),
    ("Total Changes", "COUNTROWS ( changes )", "#,0", "Counts"),
    ("High Impact", 'CALCULATE ( [Total Changes], changes[impact] = "High" )', "#,0", "Counts"),
    ("Open Actions", 'CALCULATE ( [Total Changes], changes[action_req] = 1, changes[status] <> "Actioned" )', "#,0", "Actions"),
    ("Due In 30 Days", "VAR t = [As Of Date] RETURN CALCULATE ( [Open Actions], FILTER ( ALL ( changes[deadline] ), NOT ISBLANK ( changes[deadline] ) && changes[deadline] >= t && changes[deadline] <= t + 30 ) )", "#,0", "Actions"),
    ("Overdue Actions", "VAR t = [As Of Date] RETURN CALCULATE ( [Open Actions], FILTER ( ALL ( changes[deadline] ), NOT ISBLANK ( changes[deadline] ) && changes[deadline] < t ) )", "#,0", "Actions"),
    ("Action Rate", "DIVIDE ( [Open Actions], [Total Changes] )", "0%", "Actions"),
    ("Changes Last 30 Days", "VAR t = [As Of Date] RETURN CALCULATE ( [Total Changes], FILTER ( ALL ( changes[published] ), changes[published] > t - 30 && changes[published] <= t ) )", "#,0", "Trend"),
    ("Changes Prior 30 Days", "VAR t = [As Of Date] RETURN CALCULATE ( [Total Changes], FILTER ( ALL ( changes[published] ), changes[published] > t - 60 && changes[published] <= t - 30 ) )", "#,0", "Trend"),
    ("Change vs Prior 30 Days", "DIVIDE ( [Changes Last 30 Days] - [Changes Prior 30 Days], [Changes Prior 30 Days] )", "0%", "Trend"),
    ("Sample Data Note", 'IF ( MAX ( changes[data_type] ) = "Live", "Live data from the weekly monitor. Keyword classification, not legal advice.", "Synthetic sample data. Keyword classification, not legal advice." )', None, "Labels"),
    ("Deadline Color", 'VAR d = MIN ( changes[Days To Deadline] ) RETURN IF ( ISBLANK ( d ), BLANK (), IF ( d >= 9999, "#8A97A5", IF ( d < 0, "#C0392B", IF ( d <= 30, "#D98E04", "#1F2933" ) ) ) )', None, None),
    ("Heat Color", 'VAR n = [Total Changes] RETURN IF ( ISBLANK ( n ), BLANK (), IF ( n <= 10, "#F1F7DA", IF ( n <= 25, "#DDEBA6", IF ( n <= 45, "#C8E070", "#A9CF3A" ) ) ) )', None, None),
]
CALC_COLUMNS = {
    "quality_checks": [("Latest Load", "text", 'IF ( quality_checks[run_date] = MAX ( quality_checks[run_date] ), "Yes", "No" )')],
    "changes": [
        ("Days To Deadline", "int", "VAR t = COALESCE ( MAXX ( ALL ( dashboard_changes ), dashboard_changes[as_of] ), TODAY () ) RETURN IF ( ISBLANK ( changes[deadline] ), BLANK (), DATEDIFF ( t, changes[deadline], DAY ) )"),
        ("Deadline Bucket", "text", 'VAR t = COALESCE ( MAXX ( ALL ( dashboard_changes ), dashboard_changes[as_of] ), TODAY () ) RETURN IF ( ISBLANK ( changes[deadline] ), "No fixed date", IF ( changes[deadline] < t, "Overdue", IF ( changes[deadline] <= t + 30, "Due in 30 days", "Later" ) ) )'),
    ],
}
CALC_TABLES = {
    "open_actions": ('SELECTCOLUMNS ( FILTER ( changes, changes[action_req] = 1 && changes[status] <> "Actioned" ), "Title", changes[title], "Agency", changes[source], "Impact", changes[impact], "Deadline", changes[deadline], "Days To Deadline", changes[Days To Deadline], "Status", changes[status] )',
                     [("Title", "text"), ("Agency", "text"), ("Impact", "text"), ("Deadline", "date"), ("Days To Deadline", "int"), ("Status", "text")],
                     [("Days Left", "int", "IF ( ISBLANK ( open_actions[Days To Deadline] ), 9999, open_actions[Days To Deadline] )")]),
    "dim_topic": ('DISTINCT ( SELECTCOLUMNS ( change_topics, "topic", change_topics[topic] ) )', [("topic", "text")], []),
    "dim_department": ('DATATABLE ( "department", STRING, "sort", INTEGER, { { "Accounts & Trust", 1 }, { "Compliance & AML", 2 }, { "HR & Payroll", 3 }, { "Property", 4 }, { "Privacy & IT", 5 } } )',
                       [("department", "text"), ("sort", "int")], []),
    "topic_department": ('DATATABLE ( "topic", STRING, "department", STRING, { { "AML/CTF", "Compliance & AML" }, { "Sanctions", "Compliance & AML" }, { "Trust Accounts", "Accounts & Trust" }, { "Tax", "Accounts & Trust" }, { "Payroll", "HR & Payroll" }, { "Payroll", "Accounts & Trust" }, { "Superannuation", "HR & Payroll" }, { "Superannuation", "Accounts & Trust" }, { "Employment", "HR & Payroll" }, { "Property", "Property" }, { "Privacy & Data", "Privacy & IT" } } )',
                         [("topic", "text"), ("department", "text")], []),
}
# (from many, to one, active, cross-filter both)
RELATIONSHIPS = [
    ("changes.published", "dim_date.date", True, False),
    ("changes.deadline", "dim_date.date", False, False),
    ("change_topics.id", "changes.id", True, True),
    ("change_audiences.id", "changes.id", True, True),
    ("change_effort.id", "dashboard_changes.id", True, False),
    # department pages and the department x agency heatmap: a department reaches its changes through its topics
    ("topic_department.department", "dim_department.department", True, False),
    ("topic_department.topic", "dim_topic.topic", True, True),
    ("change_topics.topic", "dim_topic.topic", True, False),
]
MEASURES = {
    "changes": [(m, e, f) for m, e, f, _ in V1_MEASURES],
    "dashboard_changes": [
        ("Changes", "COUNTROWS ( dashboard_changes ) + 0", "#,0"),
        ("New This Week", "VAR asOf = MAX ( dashboard_changes[as_of] ) RETURN CALCULATE ( COUNTROWS ( dashboard_changes ), dashboard_changes[first_seen] > asOf - 7 ) + 0", "#,0"),
        ("Needs Action", 'CALCULATE ( COUNTROWS ( dashboard_changes ), dashboard_changes[work_status] = "Outstanding" ) + 0', "#,0"),
        ("Past Target Date", 'CALCULATE ( COUNTROWS ( dashboard_changes ), dashboard_changes[work_status] = "Outstanding", dashboard_changes[days_left] < 0 ) + 0', "#,0"),
        ("One-off Cost", "SUM ( dashboard_changes[total_one_off_cost] )", "\\$#,0"),
        ("Staff Time Cost", "SUM ( dashboard_changes[internal_one_off_cost] )", "\\$#,0"),
        ("External Cost", "SUM ( dashboard_changes[external_one_off] )", "\\$#,0"),
        ("Ongoing Cost / yr", "SUM ( dashboard_changes[total_ongoing_cost_yr] )", "\\$#,0"),
        ("Backlog Hours", "SUM ( dashboard_changes[outstanding_hours] )", "#,0"),
        ("Data As At", '"Data as at " & FORMAT ( MAX ( dashboard_changes[as_of] ), "d mmm yyyy" )', None),
        ("Takeaway", '"The changes on file cost about " & FORMAT ( [One-off Cost], "$#,0" ) & " once and " & FORMAT ( [Ongoing Cost / yr], "$#,0" ) & " a year. " & FORMAT ( [Past Target Date], "0" ) & " are past their target date and the backlog is " & FORMAT ( [Backlog Hours], "#,0" ) & " staff hours."', None),
        ("Days Left Colour", 'VAR d = MAX ( dashboard_changes[days_left] ) RETURN SWITCH ( TRUE (), d < 0, "#C0392B", d < 14, "#D98C00", "#1F2933" )', None),
    ],
    "change_effort": [
        ("Outstanding Role Hours", 'CALCULATE ( SUM ( change_effort[one_off_hours] ), dashboard_changes[work_status] = "Outstanding" )', "#,0"),
    ],
    "capacity_monthly": [
        ("Hours Needed", "SUM ( capacity_monthly[hours_required] )", "#,0"),
        ("Hours Available", "SUM ( capacity_monthly[hours_available] )", "#,0"),
        ("Hours Available / Month", "AVERAGEX ( VALUES ( capacity_monthly[month_start] ), [Hours Available] )", "#,0"),
        ("Capacity Load", "DIVIDE ( [Hours Needed], [Hours Available] )", "0%"),
        ("Peak Month Load", "MAXX ( VALUES ( capacity_monthly[month_start] ), [Capacity Load] )", "0%"),
        ("Capacity Takeaway", 'VAR pm = MAXX ( TOPN ( 1, VALUES ( capacity_monthly[month_start] ), [Capacity Load] ), capacity_monthly[month_start] ) '
         'VAR need = CALCULATE ( [Hours Needed], capacity_monthly[month_start] = pm ) VAR av = CALCULATE ( [Hours Available], capacity_monthly[month_start] = pm ) '
         'RETURN "Money is manageable, hours are not: " & FORMAT ( pm, "mmm yyyy" ) & " needs " & FORMAT ( need, "#,0" ) & " hours against " '
         '& FORMAT ( av, "#,0" ) & " available. Short-term help for that month covers it."', None),
        ("Peak Month", 'FORMAT ( MAXX ( TOPN ( 1, VALUES ( capacity_monthly[month_start] ), [Capacity Load] ), capacity_monthly[month_start] ), "mmm yyyy" )', None),
        ("Hours Over Capacity", "SUM ( capacity_monthly[hours_over_capacity] )", "#,0"),
        ("FTE Gap (months)", "DIVIDE ( [Hours Over Capacity], 152 )", "0.0"),
        ("Load Colour", 'VAR l = [Capacity Load] RETURN SWITCH ( TRUE (), ISBLANK ( l ), BLANK (), l > 1, "#E8A29A", l > 0.8, "#F3D27A", "#D9EC9A" )', None),
    ],
    "run_log": [
        ("Sources Checked", "VAR d = INT ( MAX ( run_log[run_at] ) ) RETURN COUNTROWS ( FILTER ( run_log, INT ( run_log[run_at] ) = d ) ) + 0", "#,0"),
        ("Sources OK", 'VAR d = INT ( MAX ( run_log[run_at] ) ) RETURN COUNTROWS ( FILTER ( run_log, INT ( run_log[run_at] ) = d && LEFT ( run_log[status], 2 ) = "ok" ) ) + 0', "#,0"),
        ("Sources OK Label", 'IF ( [Sources Checked] = 0, "n/a (sample)", FORMAT ( [Sources OK], "0" ) & " / " & FORMAT ( [Sources Checked], "0" ) )', None),
    ],
    "weekly_snapshot": [
        ("Weekly Runs", "COUNTROWS ( weekly_snapshot ) + 0", "#,0"),
        ("Latest Run", "MAX ( weekly_snapshot[run_date] )", "d mmm yyyy"),
        ("Changes On File (run)", "VAR d = MAX ( weekly_snapshot[run_date] ) RETURN CALCULATE ( SUM ( weekly_snapshot[changes_on_file] ), weekly_snapshot[run_date] = d )", "#,0"),
        ("New Changes (run)", "SUM ( weekly_snapshot[new_this_run] )", "#,0"),
        ("Needs Action (run)", "VAR d = MAX ( weekly_snapshot[run_date] ) RETURN CALCULATE ( SUM ( weekly_snapshot[needs_action] ), weekly_snapshot[run_date] = d )", "#,0"),
        ("Past Target (run)", "VAR d = MAX ( weekly_snapshot[run_date] ) RETURN CALCULATE ( SUM ( weekly_snapshot[past_target_date] ), weekly_snapshot[run_date] = d )", "#,0"),
        ("Backlog Hours (run)", "VAR d = MAX ( weekly_snapshot[run_date] ) RETURN CALCULATE ( SUM ( weekly_snapshot[backlog_hours] ), weekly_snapshot[run_date] = d )", "#,0"),
        ("Backlog vs 4 Weeks", "VAR d = MAX ( weekly_snapshot[run_date] ) "
                               "VAR p = CALCULATE ( MAX ( weekly_snapshot[run_date] ), ALL ( weekly_snapshot ), weekly_snapshot[run_date] <= d - 28 ) "
                               "RETURN IF ( ISBLANK ( p ), BLANK (), [Backlog Hours (run)] - CALCULATE ( SUM ( weekly_snapshot[backlog_hours] ), ALL ( weekly_snapshot ), weekly_snapshot[run_date] = p ) )",
         "+#,0;-#,0;0"),
        ("Trend Takeaway", 'VAR d = MAX ( weekly_snapshot[run_date] ) '
                           'VAR p = CALCULATE ( MAX ( weekly_snapshot[run_date] ), ALL ( weekly_snapshot ), weekly_snapshot[run_date] <= d - 28 ) '
                           'VAR late_then = CALCULATE ( SUM ( weekly_snapshot[past_target_date] ), ALL ( weekly_snapshot ), weekly_snapshot[run_date] = p ) '
                           'RETURN IF ( [Weekly Runs] = 0, "No weekly history yet: it builds up from the first Databricks load.", '
                           '"Backlog " & FORMAT ( [Backlog Hours (run)], "#,0" ) & " hours, " & IF ( [Backlog vs 4 Weeks] >= 0, "up ", "down " ) '
                           '& FORMAT ( ABS ( [Backlog vs 4 Weeks] ), "#,0" ) & " in four weeks; " & FORMAT ( [Past Target (run)], "0" ) '
                           '& " changes past their target date (" & FORMAT ( late_then, "0" ) & " four weeks earlier)." )', None),
    ],
    "quality_checks": [
        ("Checks Passed Label", 'VAR d = MAX ( quality_checks[run_date] ) VAR n = CALCULATE ( COUNTROWS ( quality_checks ), quality_checks[run_date] = d ) '
                                'VAR ok = COUNTROWS ( FILTER ( ALL ( quality_checks ), quality_checks[run_date] = d && UPPER ( quality_checks[passed] ) = "TRUE" ) ) + 0 '
                                'RETURN IF ( n = 0, "n/a", FORMAT ( ok, "0" ) & " / " & FORMAT ( n, "0" ) )', None),
        ("Check Colour", 'IF ( UPPER ( SELECTEDVALUE ( quality_checks[passed] ) ) = "TRUE", "#5F7A1A", IF ( UPPER ( SELECTEDVALUE ( quality_checks[blocking] ) ) = "TRUE", "#C0392B", "#D98C00" ) )', None),
    ],
}


FOLDERS = {m: f for m, _, _, f in V1_MEASURES if f}
SORT_BY = {("dim_date", "month_name"): "month_num"}


def _tag(*parts) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "/".join(parts)))


def _q(name: str) -> str:
    return f"'{name}'" if any(ch in name for ch in " /()-&") else name


def _measures(table: str) -> list[str]:
    out = []
    for m, expr, fmt in MEASURES.get(table, []):
        out.append(f"\tmeasure {_q(m)} = {expr}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        if m in FOLDERS:
            out.append(f"\t\tdisplayFolder: {FOLDERS[m]}")
        out += [f"\t\tlineageTag: {_tag(table, m)}", ""]
    return out


def _column(table: str, c: str, t: str, source: str | None = None, expr: str | None = None) -> list[str]:
    head = f"\tcolumn {_q(c)} = {expr}" if expr else f"\tcolumn {_q(c)}"
    out = [head, f"\t\tdataType: {TYPES[t][0]}"]
    if t == "date":
        out.append("\t\tformatString: d mmm yyyy")
    out.append("\t\tsummarizeBy: none")
    if source:
        out.append(f"\t\tsourceColumn: {source}")
    if (table, c) in SORT_BY:
        out.append(f"\t\tsortByColumn: {SORT_BY[(table, c)]}")
    out += [f"\t\tlineageTag: {_tag(table, c)}", ""]
    return out


def _tmdl_table(name: str) -> str:
    file, optional, cols = TABLES[name]
    lines = [f"table {name}", f"\tlineageTag: {_tag(name)}", ""] + _measures(name)
    for c, t in cols:
        lines += _column(name, c, t, source=c)
    for c, t, expr in CALC_COLUMNS.get(name, []):
        lines += _column(name, c, t, expr=expr)
    src = _source(name, file, [(c, TYPES[t][1]) for c, t in cols], optional)
    lines += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource ="]
    lines += ["\t\t\t\t" + ln for ln in src.splitlines()]
    return "\n".join(lines) + "\n"


def _tmdl_calc_table(name: str) -> str:
    expr, cols, calc_cols = CALC_TABLES[name]
    lines = [f"table {name}", f"\tlineageTag: {_tag(name)}", ""] + _measures(name)
    for c, t in cols:
        lines += _column(name, c, t, source=f"[{c}]")
    for c, t, e in calc_cols:
        lines += _column(name, c, t, expr=e)
    lines += [f"\tpartition {name} = calculated", "\t\tmode: import", f"\t\tsource = {expr}"]
    return "\n".join(lines) + "\n"


def build_model() -> None:
    d = MODEL / "definition"
    (d / "tables").mkdir(parents=True, exist_ok=True)
    (MODEL / "definition.pbism").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}}, indent=2))
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n")
    all_tables = [*TABLES, *CALC_TABLES]
    order = json.dumps(["Source", "Branch", "Dataset", "DatabricksHost", "DatabricksHttpPath", "DatabricksCatalog", *TABLES])
    (d / "model.tmdl").write_text(
        "model Model\n\tculture: en-AU\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tsourceQueryCulture: en-AU\n"
        "\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
        f"annotation PBI_QueryOrder = {order}\n\n" + "".join(f"ref table {t}\n" for t in all_tables))
    (d / "expressions.tmdl").write_text(
        'expression Branch = "main" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {_tag('Branch')}\n\n"
        '\tannotation PBI_ResultType = Text\n\n'
        'expression Dataset = "bi_export" meta [IsParameterQuery = true, List = {"bi_export", "data/live"}, '
        'DefaultValue = "bi_export", Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {_tag('Dataset')}\n\n"
        '\tannotation PBI_ResultType = Text\n\n'
        'expression Source = "GitHub CSV" meta [IsParameterQuery = true, List = {"GitHub CSV", "Databricks"}, '
        'DefaultValue = "GitHub CSV", Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {_tag('Source')}\n\n"
        '\tannotation PBI_ResultType = Text\n\n'
        'expression DatabricksHost = "dbc-xxxxxxxx-xxxx.cloud.databricks.com" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = false]\n'
        f"\tlineageTag: {_tag('DatabricksHost')}\n\n"
        '\tannotation PBI_ResultType = Text\n\n'
        'expression DatabricksHttpPath = "/sql/1.0/warehouses/xxxxxxxxxxxxxxxx" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = false]\n'
        f"\tlineageTag: {_tag('DatabricksHttpPath')}\n\n"
        '\tannotation PBI_ResultType = Text\n\n'
        'expression DatabricksCatalog = "workspace" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = false]\n'
        f"\tlineageTag: {_tag('DatabricksCatalog')}\n\n"
        '\tannotation PBI_ResultType = Text\n')
    rel = []
    for frm, to, active, both in RELATIONSHIPS:
        rel += [f"relationship {_tag(frm, to)}"]
        if not active:
            rel.append("\tisActive: false")
        if both:
            rel.append("\tcrossFilteringBehavior: bothDirections")
        rel += [f"\tfromColumn: {frm}", f"\ttoColumn: {to}", ""]
    (d / "relationships.tmdl").write_text("\n".join(rel))
    for t in TABLES:
        (d / "tables" / f"{t}.tmdl").write_text(_tmdl_table(t))
    for t in CALC_TABLES:
        (d / "tables" / f"{t}.tmdl").write_text(_tmdl_calc_table(t))


# ---------------------------------------------------------------------------------------------------- report
def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def colour(hex_):
    return {"solid": {"color": lit(f"'{hex_}'")}}


def field(entity, prop, measure=False):
    return {("Measure" if measure else "Column"): {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def proj(entity, prop, measure=False, name=None, active=False):
    p = {"field": field(entity, prop, measure), "queryRef": f"{entity}.{prop}", "nativeQueryRef": name or prop}
    if name:
        p["displayName"] = name
    if active:
        p["active"] = True
    return p


NO_FRAME = {"background": [{"properties": {"show": lit("false")}}], "border": [{"properties": {"show": lit("false")}}]}


def container(name, box, visual, z, extra=None):
    x0, y0, x1, y1 = box
    v = {"$schema": VC_SCHEMA, "name": name,
         "position": {"x": x0, "y": y0, "z": z, "height": y1 - y0, "width": x1 - x0, "tabOrder": z}, "visual": visual}
    v["visual"].setdefault("visualContainerObjects", NO_FRAME)
    v["visual"]["drillFilterOtherVisuals"] = True
    if extra:
        v.update(extra)
    return v


def card(entity, measure, size=34, colour_hex=None):
    return {"visualType": "cardVisual",
            "query": {"queryState": {"Data": {"projections": [proj(entity, measure, True)]}}},
            "objects": {"value": [{"properties": {"fontColor": colour(colour_hex or TOKENS["lime"]), "fontSize": lit(f"{size}D")}}],
                        "label": [{"properties": {"show": lit("false")}}],
                        "fillCustom": [{"properties": {"show": lit("false")}}],
                        "outline": [{"properties": {"show": lit("false")}}, ], }}


def kpi_boxes(n):
    gap = 20
    tw = (CONTENT_X1 - CONTENT_X0 - gap * (n - 1)) // n
    return [(CONTENT_X0 + i * (tw + gap) + 10, KPI_Y[0] + 40, CONTENT_X0 + i * (tw + gap) + tw - 10, KPI_Y[1] - 8) for i in range(n)]


def inner(box, top=52, pad=12):
    x0, y0, x1, y1 = box
    return (x0 + pad, y0 + top, x1 - pad, y1 - pad)


def nav_button(owner: str, i: int, target: str) -> dict:
    y = NAV_Y0 + i * NAV_STEP
    return container(f"nav_{owner[-6:]}_{i:02d}", (30, y, 330, y + 56), {
        "visualType": "actionButton",
        "objects": {"icon": [{"properties": {"shapeType": lit("'blank'")}}], "fill": [{"properties": {"show": lit("false")}}],
                    "outline": [{"properties": {"show": lit("false")}}], "text": [{"properties": {"show": lit("false")}}]},
        "visualContainerObjects": {**NO_FRAME, "visualLink": [{"properties": {
            "show": lit("true"), "type": lit("'PageNavigation'"), "navigationSection": lit(f"'{target}'")}}]}}, 9000 + i)


def slicer(name, box, entity, col, title, z, group):
    return container(name, box, {
        "visualType": "slicer", "query": {"queryState": {"Values": {"projections": [proj(entity, col, active=True)]}}},
        "objects": {"data": [{"properties": {"mode": lit("'Dropdown'")}}], "header": [{"properties": {"show": lit("false")}}],
                    "items": [{"properties": {"fontColor": colour(TOKENS["ink"]), "background": colour("#EEF5D3"), "textSize": lit("12D")}}],
                    "selection": [{"properties": {"selectAllCheckboxEnabled": lit("true")}}]},
        "visualContainerObjects": {**NO_FRAME, "title": [{"properties": {
            "show": lit("true"), "text": lit(f"'{title}'"), "fontColor": colour(TOKENS["lime"]), "fontSize": lit("11D"),
            "background": colour(TOKENS["ink"])}}]}}, z, {"syncGroup": {"groupName": group, "fieldChanges": True, "filterChanges": True}})


def page_finance(p):
    P = p["panels"]
    k = kpi_boxes(5)
    E = "dashboard_changes"
    vs = [container(f"kpi{i}0000000000000000", k[i], card(E, m, colour_hex=c), 1000 + i)
          for i, (m, c) in enumerate([("New This Week", None), ("Needs Action", None), ("Past Target Date", "#F0B4AC"),
                                       ("One-off Cost", None), ("Backlog Hours", None)])]
    vs.append(container("takeaway00000000000", (372, 248, 1884, 300), {
        **card(E, "Takeaway", 17, TOKENS["ink"]),
        "visualContainerObjects": {"background": [{"properties": {"show": lit("true"), "color": colour("#D9EC9A"), "transparency": lit("0D")}}],
                                   "border": [{"properties": {"show": lit("false")}}]}}, 1010))
    table_cols = [("title", "Change"), ("source", "Agency"), ("impact", "Impact"), ("target_date", "Target date"),
                  ("days_left", "Days left"), ("total_one_off_cost", "Cost"), ("lead_role", "Lead")]
    widths = {"title": 330, "source": 90, "impact": 80, "target_date": 110, "days_left": 80, "total_one_off_cost": 80, "lead_role": 150}
    vs.append(container("tbl00000000000000000", inner(P["table"][0], 96), {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": [proj(E, c, name=n) for c, n in table_cols]}},
                  "sortDefinition": {"sort": [{"field": field(E, "days_left"), "direction": "Ascending"}]}},
        "objects": {
            "values": [{"properties": {"fontSize": lit("12D")}},
                       {"properties": {"fontColor": {"solid": {"color": {"expr": field(E, "Days Left Colour", True)}}}},
                        "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{E}.days_left"}}],
            "columnHeaders": [{"properties": {"fontSize": lit("12D"), "bold": lit("true")}}],
            "total": [{"properties": {"totals": lit("false")}}],
            "columnWidth": [{"properties": {"value": lit(f"{w}D")}, "selector": {"metadata": f"{E}.{c}"}} for c, w in widths.items()]}},
        1020, {"filterConfig": {"filters": [{"name": "f_out", "field": field(E, "work_status"), "type": "Categorical", "filter": {
            "Version": 2, "From": [{"Name": "d", "Entity": E, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": "work_status"}}],
                                            "Values": [[{"Literal": {"Value": "'Outstanding'"}}]]}}}]}}]}}))
    tx0, ty0, tx1, _ = P["table"][0]
    vs.append(slicer("slAgency00000000000", (tx0 + 12, ty0 + 52, tx0 + 290, ty0 + 92), E, "source", "Agency", 1030, "sl_agency"))
    vs.append(slicer("slImpact00000000000", (tx0 + 304, ty0 + 52, tx0 + 582, ty0 + 92), E, "impact", "Impact", 1031, "sl_impact"))
    vs.append(container("costbar000000000000", inner(P["cost"][0]), {
        "visualType": "barChart",
        "query": {"queryState": {"Category": {"projections": [proj(E, "lead_department", active=True, name="Department")]},
                                 "Y": {"projections": [proj(E, "Staff Time Cost", True), proj(E, "External Cost", True)]}}},
        "objects": {"labels": [{"properties": {"show": lit("true"), "fontSize": lit("11D")}}],
                    "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}],
                    "dataPoint": [{"properties": {"fill": colour(TOKENS["slate"])}, "selector": {"metadata": f"{E}.Staff Time Cost"}},
                                  {"properties": {"fill": colour(TOKENS["lime"])}, "selector": {"metadata": f"{E}.External Cost"}}]}}, 1040))
    C = "capacity_monthly"
    vs.append(container("peoplebar0000000000", inner(P["people"][0]), {
        "visualType": "clusteredBarChart",
        "query": {"queryState": {"Category": {"projections": [proj(C, "role", active=True, name="Role")]},
                                 "Y": {"projections": [proj(C, "Hours Needed", True), proj(C, "Hours Available / Month", True)]}},
                  "sortDefinition": {"sort": [{"field": field(C, "Hours Needed", True), "direction": "Descending"}]}},
        "objects": {"labels": [{"properties": {"show": lit("true"), "fontSize": lit("10D")}}],
                    "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}],
                    "dataPoint": [{"properties": {"fill": colour(TOKENS["lime_dark"])}, "selector": {"metadata": f"{C}.Hours Needed"}},
                                  {"properties": {"fill": colour(TOKENS["muted"])}, "selector": {"metadata": f"{C}.Hours Available / Month"}}]}}, 1050))
    return vs


def page_trend(p):
    P = p["panels"]
    k = kpi_boxes(5)
    S, Q = "weekly_snapshot", "quality_checks"
    vs = [container(f"kpt{i}0000000000000000", k[i], card(t, m), 1000 + i)
          for i, (t, m) in enumerate([(S, "Weekly Runs"), (S, "Changes On File (run)"), (S, "Backlog Hours (run)"),
                                      (S, "Backlog vs 4 Weeks"), (Q, "Checks Passed Label")])]
    vs.append(container("takeawayt0000000000", (372, 248, 1884, 300), {
        **card(S, "Trend Takeaway", 17, TOKENS["ink"]),
        "visualContainerObjects": {"background": [{"properties": {"show": lit("true"), "color": colour("#D9EC9A"), "transparency": lit("0D")}}],
                                   "border": [{"properties": {"show": lit("false")}}]}}, 1006))
    week = proj(S, "run_date", active=True, name="Week")
    cat_axis = [{"properties": {"axisType": lit("'Categorical'"), "showAxisTitle": lit("false")}}]
    vs.append(container("trendbacklog0000000", inner(P["backlog"][0]), {
        "visualType": "lineClusteredColumnComboChart",
        "query": {"queryState": {"Category": {"projections": [week]},
                                 "Y": {"projections": [proj(S, "Needs Action (run)", True)]},
                                 "Y2": {"projections": [proj(S, "Backlog Hours (run)", True)]}},
                  "sortDefinition": {"sort": [{"field": field(S, "run_date"), "direction": "Ascending"}]}},
        "objects": {"dataPoint": [{"properties": {"fill": colour(TOKENS["slate"])}, "selector": {"metadata": f"{S}.Needs Action (run)"}},
                                  {"properties": {"fill": colour(TOKENS["lime_dark"])}, "selector": {"metadata": f"{S}.Backlog Hours (run)"}}],
                    "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}],
                    "categoryAxis": cat_axis}}, 1010))
    vs.append(container("trendvolume00000000", inner(P["volume"][0]), {
        "visualType": "lineClusteredColumnComboChart",
        "query": {"queryState": {"Category": {"projections": [week]},
                                 "Y": {"projections": [proj(S, "New Changes (run)", True)]},
                                 "Y2": {"projections": [proj(S, "Changes On File (run)", True)]}},
                  "sortDefinition": {"sort": [{"field": field(S, "run_date"), "direction": "Ascending"}]}},
        "objects": {"dataPoint": [{"properties": {"fill": colour(TOKENS["lime"])}, "selector": {"metadata": f"{S}.New Changes (run)"}},
                                  {"properties": {"fill": colour(TOKENS["slate"])}, "selector": {"metadata": f"{S}.Changes On File (run)"}}],
                    "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}],
                    "categoryAxis": cat_axis}}, 1020))
    vs.append(container("trendlate000000000", inner(P["late"][0]), {
        "visualType": "lineChart",
        "query": {"queryState": {"Category": {"projections": [week]},
                                 "Y": {"projections": [proj(S, "Past Target (run)", True)]}},
                  "sortDefinition": {"sort": [{"field": field(S, "run_date"), "direction": "Ascending"}]}},
        "objects": {"dataPoint": [{"properties": {"fill": colour("#C8553D")}}],
                    "lineStyles": [{"properties": {"strokeWidth": lit("3D"), "showMarker": lit("true")}}],
                    "labels": [{"properties": {"show": lit("false")}}],
                    "categoryAxis": cat_axis}}, 1030))
    vs.append(container("quality000000000000", inner(P["quality"][0]), {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": [proj(Q, "check_name", name="Check"), proj(Q, "blocking", name="Blocking"),
                                                            proj(Q, "failed_rows", name="Failed rows"), proj(Q, "passed", name="Passed")]}},
                  "sortDefinition": {"sort": [{"field": field(Q, "check_name"), "direction": "Ascending"}]}},
        "objects": {"values": [{"properties": {"fontSize": lit("12D")}},
                               {"properties": {"fontColor": {"solid": {"color": {"expr": field(Q, "Check Colour", True)}}}},
                                "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{Q}.passed"}}],
                    "columnHeaders": [{"properties": {"fontSize": lit("12D"), "bold": lit("true")}}],
                    "total": [{"properties": {"totals": lit("false")}}],
                    "columnWidth": [{"properties": {"value": lit("300D")}, "selector": {"metadata": f"{Q}.check_name"}},
                                    {"properties": {"value": lit("80D")}, "selector": {"metadata": f"{Q}.blocking"}},
                                    {"properties": {"value": lit("90D")}, "selector": {"metadata": f"{Q}.failed_rows"}},
                                    {"properties": {"value": lit("70D")}, "selector": {"metadata": f"{Q}.passed"}}]}},
        1040, {"filterConfig": {"filters": [{"name": "f_latest", "field": field(Q, "Latest Load"), "type": "Categorical", "filter": {
            "Version": 2, "From": [{"Name": "q", "Entity": Q, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "q"}}, "Property": "Latest Load"}}],
                                            "Values": [[{"Literal": {"Value": "'Yes'"}}]]}}}]}}]}}))
    return vs


def page_capacity(p):
    P = p["panels"]
    k = kpi_boxes(5)
    C, E, L, F = "capacity_monthly", "dashboard_changes", "run_log", "change_effort"
    vs = [container(f"kpc{i}0000000000000000", k[i], card(t, m), 1000 + i)
          for i, (t, m) in enumerate([(C, "Peak Month Load"), (C, "Hours Over Capacity"), (C, "FTE Gap (months)"),
                                      (E, "Ongoing Cost / yr"), (L, "Sources OK Label")])]
    vs.append(container("takeawayc0000000000", (372, 248, 1884, 300), {
        **card(C, "Capacity Takeaway", 17, TOKENS["ink"]),
        "visualContainerObjects": {"background": [{"properties": {"show": lit("true"), "color": colour("#D9EC9A"), "transparency": lit("0D")}}],
                                   "border": [{"properties": {"show": lit("false")}}]}}, 1006))
    vs.append(container("heat000000000000000", inner(P["heat"][0]), {
        "visualType": "pivotTable",
        "query": {"queryState": {"Rows": {"projections": [proj(C, "role", active=True, name="Role")]},
                                 "Columns": {"projections": [proj(C, "month_start", active=True, name="Month")]},
                                 "Values": {"projections": [proj(C, "Capacity Load", True)]}}},
        "objects": {"values": [{"properties": {"fontSize": lit("12D")}},
                               {"properties": {"backColor": {"solid": {"color": {"expr": field(C, "Load Colour", True)}}}},
                                "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{C}.Capacity Load"}}],
                    "columnHeaders": [{"properties": {"fontSize": lit("12D")}}], "rowHeaders": [{"properties": {"fontSize": lit("12D")}}],
                    "subTotals": [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}]}}, 1010))
    vs.append(container("roles00000000000000", inner(P["roles"][0]), {
        "visualType": "barChart",
        "query": {"queryState": {"Category": {"projections": [proj(F, "role", active=True, name="Role")]},
                                 "Y": {"projections": [proj(F, "Outstanding Role Hours", True)]}},
                  "sortDefinition": {"sort": [{"field": field(F, "Outstanding Role Hours", True), "direction": "Descending"}]}},
        "objects": {"labels": [{"properties": {"show": lit("true"), "fontSize": lit("11D")}}],
                    "dataPoint": [{"properties": {"fill": colour(TOKENS["slate"])}}], "legend": [{"properties": {"show": lit("false")}}]}}, 1020))
    vs.append(container("due0000000000000000", inner(P["due"][0]), {
        "visualType": "columnChart",
        "query": {"queryState": {"Category": {"projections": [proj(E, "target_date", active=True, name="Target month")]},
                                 "Y": {"projections": [proj(E, "Backlog Hours", True)]}}},
        "objects": {"labels": [{"properties": {"show": lit("true"), "fontSize": lit("10D")}}],
                    "dataPoint": [{"properties": {"fill": colour(TOKENS["lime_dark"])}}],
                    "categoryAxis": [{"properties": {"axisType": lit("'Categorical'")}}]}}, 1030))
    vs.append(container("log0000000000000000", inner(P["log"][0]), {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": [proj(L, "run_at", name="Run"), proj(L, "agency", name="Agency"),
                                                            proj(L, "status", name="Status"), proj(L, "items", name="Items")]}},
                  "sortDefinition": {"sort": [{"field": field(L, "run_at"), "direction": "Descending"}]}},
        "objects": {"values": [{"properties": {"fontSize": lit("11D")}}],
                    "columnHeaders": [{"properties": {"fontSize": lit("12D"), "bold": lit("true")}}],
                    "total": [{"properties": {"totals": lit("false")}}],
                    "columnWidth": [{"properties": {"value": lit("110D")}, "selector": {"metadata": f"{L}.run_at"}},
                                    {"properties": {"value": lit("160D")}, "selector": {"metadata": f"{L}.agency"}},
                                    {"properties": {"value": lit("440D")}, "selector": {"metadata": f"{L}.status"}},
                                    {"properties": {"value": lit("60D")}, "selector": {"metadata": f"{L}.items"}}]}}, 1040))
    return vs


def _nav_target(v: dict) -> str | None:
    try:
        link = v["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]
        if link["type"]["expr"]["Literal"]["Value"] == "'PageNavigation'":
            return link["navigationSection"]["expr"]["Literal"]["Value"].strip("'")
    except (KeyError, IndexError, TypeError):
        return None
    return None


BUCKET_COLOURS = [("Overdue", "#c8553d"), ("Due in 30 days", "#b6d94c"), ("Later", "#46586b"), ("No fixed date", "#c3ccd6")]
ABOUT = [
    ("How to read this report", None, "24pt"),
    ("Impact:  ", "High / Medium / Low, set by keyword rules (penalty, mandatory, must ...).", "16pt"),
    ("Action required:  ", "The change states an obligation or a step the firm must take.", "16pt"),
    ("Open action:  ", "Action required and the status is not Actioned.", "16pt"),
    ("Deadline / Days left:  ", "Date taken from the text of the change; days left are counted from the date of the data "
                                "(not the day the file is opened). Red = overdue, amber = due within 30 days.", "16pt"),
    ("Departments:  ", "A change reaches a department through its topics (AML/CTF and Sanctions go to Compliance, "
                       "Payroll and Super to HR and to Accounts ...), so department totals add up to more than the firm total.", "16pt"),
    ("Heatmap:  ", "Department x agency; a darker green cell means more changes.", "16pt"),
    ("Cost and hours:  ", "Staff time x loaded hourly rate + external spend (advisers, systems), from stated assumptions "
                          "in impact_model.py. Not quotes and not legal advice.", "16pt"),
    ("Capacity:  ", "Hours each role needs for regulatory work in a month against the hours it has for it.", "16pt"),
    ("Weekly trend:  ", "One row per weekly run, kept in the Databricks lakehouse (bronze, quality gate, silver, gold). "
                        "In sample mode the synthetic year is replayed week by week through the same pipeline.", "16pt"),
    ("Data:  ", "Source = GitHub CSV (Dataset = bi_export synthetic year or data/live weekly monitor) or Databricks (gold tables). "
                "Source health always shows the latest real weekly run.", "16pt"),
]


def patch_v1_visuals(pages: Path) -> None:
    """Fixes to the v1 pages: tables sorted by urgency, the agency chart split by deadline, the About text."""
    days = {"Column": {"Expression": {"SourceRef": {"Entity": "changes"}}, "Property": "Days To Deadline"}}
    for vf in pages.glob("*/visuals/*/visual.json"):
        v = json.loads(vf.read_text())
        vis = v.get("visual", {})
        t = vis.get("visualType")
        q = vis.get("query", {})
        fields = json.dumps(q)
        if t == "tableEx" and "Days To Deadline" in fields and "sortDefinition" not in q:
            q["sortDefinition"] = {"sort": [{"field": days, "direction": "Ascending"}]}   # most overdue first
        elif t == "barChart" and '"Overdue Actions"' in fields and '"source"' in fields:
            # "Open actions by agency": every open action, split overdue / due soon / later (same colours as the bucket chart)
            q["queryState"]["Y"] = {"projections": [proj("changes", "Open Actions", True)]}
            q["queryState"]["Series"] = {"projections": [proj("changes", "Deadline Bucket", active=True)]}
            q["sortDefinition"] = {"sort": [{"field": field("changes", "Open Actions", True), "direction": "Descending"}]}
            vis["objects"]["dataPoint"] = [
                {"properties": {"fill": colour(c)}, "selector": {"data": [{"scopeId": {"Comparison": {
                    "ComparisonKind": 0, "Left": {"Column": {"Expression": {"SourceRef": {"Entity": "changes"}}, "Property": "Deadline Bucket"}},
                    "Right": {"Literal": {"Value": f"'{b}'"}}}}}]}} for b, c in BUCKET_COLOURS]
            vis["objects"]["legend"] = [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]
        elif t == "textbox" and "How to read this report" in json.dumps(vis.get("objects", {})):
            paras = []
            for head, body, size in ABOUT:
                if body is None:
                    paras.append({"textRuns": [{"value": head, "textStyle": {"fontSize": size, "fontWeight": "bold", "color": TOKENS["ink"]}}]})
                else:
                    paras.append({"textRuns": [{"value": head, "textStyle": {"fontSize": size, "fontWeight": "bold", "color": "#5f7a1a"}},
                                               {"value": body, "textStyle": {"fontSize": size, "color": TOKENS["ink"]}}]})
                paras.append({"textRuns": [{"value": " ", "textStyle": {"fontSize": "5pt"}}]})
            vis["objects"]["general"][0]["properties"]["paragraphs"] = paras
        else:
            continue
        vf.write_text(json.dumps(v))


def build_report() -> None:
    """Unpack the v1 report from the .pbix, repaint its sidebars, re-slot its navigation and add the new pages."""
    shutil.rmtree(REPORT, ignore_errors=True)
    with zipfile.ZipFile(PBIX) as z:
        for n in z.namelist():
            if n.startswith("Report/"):
                out = REPORT / n[len("Report/"):]
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(n))
    d, res = REPORT / "definition", REPORT / "StaticResources" / "RegisteredResources"
    (REPORT / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2))
    slot = {pid: i for i, (pid, _, _) in enumerate(NAV)}
    patch_v1_visuals(d / "pages")

    # v1 pages: repaint the sidebar with the new items, move and add navigation buttons
    for pj in sorted((d / "pages").glob("*/page.json")):
        page = json.loads(pj.read_text())
        bg = json.dumps(page.get("objects", {}))
        if "bg_" in bg:
            name = "bg_" + bg.split("bg_")[1].split(".png")[0] + ".png"
            img = Image.open(res / name).convert("RGB")
            sidebar(img, page["name"] if page["name"] in slot else None)
            img.save(res / name, optimize=True)
        vdir = pj.parent / "visuals"
        have = set()
        for vf in vdir.glob("*/visual.json"):
            v = json.loads(vf.read_text())
            target = _nav_target(v)
            if target in slot and v["position"]["x"] < 360:
                v["position"]["y"] = NAV_Y0 + slot[target] * NAV_STEP
                vf.write_text(json.dumps(v))
                have.add(target)
        if have:   # pages with a sidebar get buttons for the new items too
            for pid, i in slot.items():
                if pid not in have:
                    v = nav_button(page["name"], i, pid)
                    (vdir / v["name"]).mkdir(exist_ok=True)
                    (vdir / v["name"] / "visual.json").write_text(json.dumps(v))

    # new pages
    report = json.loads((d / "report.json").read_text())
    images = next(p for p in report["resourcePackages"] if p["name"] == "RegisteredResources")["items"]
    for p, builder in zip(NEW_PAGES, (page_finance, page_capacity, page_trend)):
        bg = f"bg_{p['id'][2:10]}.png"
        background(p, res / bg)
        if not any(i["name"] == bg for i in images):
            images.append({"name": bg, "path": bg, "type": "Image"})
        pd_ = d / "pages" / p["id"]
        (pd_ / "visuals").mkdir(parents=True, exist_ok=True)
        (pd_ / "page.json").write_text(json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": p["id"], "displayName": p["name"], "displayOption": "FitToPage", "height": H, "width": W,
            "objects": {"background": [{"properties": {"image": {"image": {
                "name": lit(f"'{bg}'"), "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": bg}}},
                "scaling": lit("'Fit'")}}, "transparency": lit("0D")}}]}}))
        for v in builder(p) + [nav_button(p["id"], i, pid) for i, (pid, _, _) in enumerate(NAV)]:
            (pd_ / "visuals" / v["name"]).mkdir(exist_ok=True)
            (pd_ / "visuals" / v["name"] / "visual.json").write_text(json.dumps(v))
    (d / "report.json").write_text(json.dumps(report))
    pages = json.loads((d / "pages" / "pages.json").read_text())
    order = [x for x in pages["pageOrder"] if x not in {p["id"] for p in NEW_PAGES}]
    at = order.index("p7tk0000000000000001")   # new pages sit before Action tracker, as in the sidebar
    pages["pageOrder"] = order[:at] + [p["id"] for p in NEW_PAGES] + order[at:]
    (d / "pages" / "pages.json").write_text(json.dumps(pages))


def build() -> None:
    shutil.rmtree(MODEL, ignore_errors=True)
    build_model()
    build_report()
    (HERE / f"{NAME}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}], "settings": {"enableAutoRecovery": True}}, indent=2))
    for folder, kind in ((REPORT, "Report"), (MODEL, "SemanticModel")):
        (folder / ".platform").write_text(json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": kind, "displayName": NAME},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, NAME + kind))}}, indent=2))
    print(f"Wrote {HERE / (NAME + '.pbip')}")


if __name__ == "__main__":
    build()
