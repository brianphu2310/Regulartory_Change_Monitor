"""Build the live Power BI project (PBIP: TMDL semantic model + PBIR report) from code.

    python powerbi/live/build_pbip.py

Writes powerbi/live/RegulatoryMonitorLive.pbip and its two folders. Open the .pbip in Power BI Desktop and press
Refresh. The model reads the CSVs straight from GitHub, so after the Monday run a Refresh shows the new week.

Design system: the same Slate & Lime tokens, sidebar, header banner, KPI tiles and panel frames as the v1 report
(powerbi/regulatory_change_monitor.pbix), so the two reports look like one product. Tokens are in TOKENS below and in
_assets/SlateLime5001.json; panel frames are drawn into the page background so visuals sit on top without borders.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
NAME = "RegulatoryMonitorLive"
REPORT = HERE / f"{NAME}.Report"
MODEL = HERE / f"{NAME}.SemanticModel"
ASSETS = HERE / "_assets"
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
PAGES = [
    {"id": "p_brief0000000000001", "name": "Weekly briefing", "icon": "◎",
     "subtitle": "What changed this week, what it costs, and who does the work",
     "kpis": ["NEW THIS WEEK", "NEEDS ACTION", "PAST TARGET DATE", "ONE-OFF COST", "BACKLOG HOURS"],
     "panels": {"table": ((372, 316, 1260, 1056), "What changed and what it costs"),
                "cost": ((1280, 316, 1884, 676), "Cost by department: staff time vs external"),
                "people": ((1280, 696, 1884, 1056), "Who does the work: hours needed vs available")}},
    {"id": "p_capac0000000000001", "name": "Capacity & sources", "icon": "▦",
     "subtitle": "Can the team absorb the backlog, and did every source answer this run?",
     "kpis": ["CAPACITY LOAD", "HOURS OVER CAPACITY", "FTE GAP (MONTHS)", "ONGOING COST / YR", "SOURCES OK"],
     "panels": {"heat": ((372, 316, 1260, 676), "Capacity load by role and month"),
                "roles": ((1280, 316, 1884, 676), "Outstanding hours by role"),
                "due": ((372, 696, 1000, 1056), "Backlog by target month"),
                "log": ((1020, 696, 1884, 1056), "Source health: latest run")}},
    {"id": "p_about0000000000001", "name": "How to read this", "icon": "i",
     "subtitle": "Method, assumptions and limits", "kpis": [], "panels": {"text": ((372, 116, 1884, 1056), "")}},
]


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


def background(page: dict, path: Path) -> None:
    T = TOKENS
    img = Image.new("RGB", (W, H), T["page"])
    d = ImageDraw.Draw(img)
    f = lambda s, b=False: ImageFont.truetype(FONT_B if b else FONT, s)

    # sidebar
    sx0, sy0, sx1, sy1 = SIDEBAR
    _shape(img, _chamfer(SIDEBAR, 22), fill_img=_gradient((sx1 - sx0 + 1, sy1 - sy0 + 1), T["slate"], T["night"]))
    d.ellipse((62, 56, 138, 132), outline=T["lime"], width=4)
    d.ellipse((70, 64, 130, 124), fill=T["ink"])
    d.text((100, 94), "BP", font=f(30, True), fill=T["lime"], anchor="mm")
    d.text((160, 80), "Brian Phu", font=f(22, True), fill=T["white"], anchor="lm")
    d.text((160, 106), "DATA ANALYST", font=f(13, True), fill=T["lime"], anchor="lm")
    d.line((46, 160, 318, 160), fill=T["lime"], width=2)
    for i, p in enumerate(PAGES):
        y = 190 + i * 66
        if p is page:
            _shape(img, _chamfer((30, y, 330, y + 56), 10), fill=T["lime"], shadow=False)
            col = T["ink"]
        else:
            col = T["white"]
        d.text((62, y + 28), p["icon"], font=f(22, True), fill=T["ink"] if p is page else T["lime"], anchor="mm")
        d.text((96, y + 28), p["name"], font=f(20, p is page), fill=col, anchor="lm")
    d.text((182, 1000), "LIVE + SAMPLE DATA", font=f(13, True), fill=T["lime"], anchor="mm")
    d.text((182, 1022), "NOT LEGAL ADVICE", font=f(13, True), fill=T["muted"], anchor="mm")

    # header banner with the lime stripe
    hx0, hy0, hx1, hy1 = HEADER
    banner = [(hx0, hy0), (hx1 - 36, hy0), (hx1, (hy0 + hy1) // 2), (hx1 - 36, hy1), (hx0, hy1)]
    _shape(img, banner, fill_img=_gradient((hx1 - hx0 + 1, hy1 - hy0 + 1), T["slate_dark"], T["slate_mid"]))
    d.polygon([(1478, hy0), (1532, hy0), (1504, hy1), (1450, hy1)], fill=T["lime"])
    d.polygon([(1550, hy0), (1574, hy0), (1546, hy1), (1522, hy1)], fill=T["slate"])
    d.text((hx0 + 34, hy0 + 26), "REGULATORY CHANGE MONITOR · LIVE", font=f(30, True), fill=T["white"], anchor="lm")
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
def _csv_source(file: str, types: list[tuple[str, str]], optional: bool = False) -> str:
    type_list = ", ".join(f'{{"{c}", {t}}}' for c, t in types)
    fetch = (f'Csv.Document(Web.Contents("https://raw.githubusercontent.com", [RelativePath = "{REPO}/" & Branch & "/" & Dataset & "/{file}"]), '
             f'[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv])')
    if optional:   # run_log.csv only exists in the live data; an empty table keeps the sample mode working
        empty = "#table(type table [" + ", ".join(f"{c} = text" for c, _ in types) + "], {})"
        body = (f"    Raw = try Table.Buffer(Table.PromoteHeaders({fetch}, [PromoteAllScalars = true])) otherwise {empty},\n"
                f"    Typed = Table.TransformColumnTypes(Raw, {{{type_list}}}, \"en-AU\")")
    else:
        body = (f"    Raw = Table.PromoteHeaders({fetch}, [PromoteAllScalars = true]),\n"
                f"    Typed = Table.TransformColumnTypes(Raw, {{{type_list}}}, \"en-AU\")")
    return f"let\n{body}\nin\n    Typed"


TYPES = {"text": ("string", "type text"), "int": ("int64", "Int64.Type"), "num": ("double", "type number"),
         "date": ("dateTime", "type date"), "dt": ("dateTime", "type datetimezone")}
TABLES = {
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
}
MEASURES = {
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
        ("Capacity Load", "DIVIDE ( [Hours Needed], [Hours Available] )", "0%"),
        ("Hours Over Capacity", "SUM ( capacity_monthly[hours_over_capacity] )", "#,0"),
        ("FTE Gap (months)", "DIVIDE ( [Hours Over Capacity], 152 )", "0.0"),
        ("Load Colour", 'VAR l = [Capacity Load] RETURN SWITCH ( TRUE (), ISBLANK ( l ), BLANK (), l > 1, "#E8A29A", l > 0.8, "#F3D27A", "#D9EC9A" )', None),
    ],
    "run_log": [
        ("Sources Checked", "VAR d = INT ( MAX ( run_log[run_at] ) ) RETURN COUNTROWS ( FILTER ( run_log, INT ( run_log[run_at] ) = d ) ) + 0", "#,0"),
        ("Sources OK", 'VAR d = INT ( MAX ( run_log[run_at] ) ) RETURN COUNTROWS ( FILTER ( run_log, INT ( run_log[run_at] ) = d && LEFT ( run_log[status], 2 ) = "ok" ) ) + 0', "#,0"),
        ("Sources OK Label", 'IF ( [Sources Checked] = 0, "n/a (sample)", FORMAT ( [Sources OK], "0" ) & " / " & FORMAT ( [Sources Checked], "0" ) )', None),
    ],
}


def _tmdl_table(name: str) -> str:
    file, optional, cols = TABLES[name]
    lines = [f"table {name}", f"\tlineageTag: {uuid.uuid5(uuid.NAMESPACE_URL, name)}", ""]
    for m, expr, fmt in MEASURES.get(name, []):
        lines.append(f"\tmeasure '{m}' = {expr}")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines += [f"\t\tlineageTag: {uuid.uuid5(uuid.NAMESPACE_URL, name + m)}", ""]
    for c, t in cols:
        dt = TYPES[t][0]
        lines += [f"\tcolumn {c}", f"\t\tdataType: {dt}"]
        if t == "date":
            lines.append("\t\tformatString: d mmm yyyy")
        lines += [f"\t\tsummarizeBy: none", f"\t\tsourceColumn: {c}",
                  f"\t\tlineageTag: {uuid.uuid5(uuid.NAMESPACE_URL, name + '.' + c)}", ""]
    src = _csv_source(file, [(c, TYPES[t][1]) for c, t in cols], optional)
    lines += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource ="]
    lines += ["\t\t\t\t" + ln for ln in src.splitlines()]
    return "\n".join(lines) + "\n"


def build_model() -> None:
    d = MODEL / "definition"
    (d / "tables").mkdir(parents=True, exist_ok=True)
    (MODEL / "definition.pbism").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}}, indent=2))
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n")
    order = json.dumps(["Branch", "Dataset", *TABLES])
    (d / "model.tmdl").write_text(
        "model Model\n\tculture: en-AU\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tsourceQueryCulture: en-AU\n"
        "\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
        f"annotation PBI_QueryOrder = {order}\n\n" + "".join(f"ref table {t}\n" for t in TABLES))
    (d / "expressions.tmdl").write_text(
        'expression Branch = "main" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {uuid.uuid5(uuid.NAMESPACE_URL, 'Branch')}\n\n"
        '\tannotation PBI_ResultType = Text\n\n'
        'expression Dataset = "bi_export" meta [IsParameterQuery = true, List = {"bi_export", "data/live"}, '
        'DefaultValue = "bi_export", Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {uuid.uuid5(uuid.NAMESPACE_URL, 'Dataset')}\n\n"
        '\tannotation PBI_ResultType = Text\n')
    (d / "relationships.tmdl").write_text(
        f"relationship {uuid.uuid5(uuid.NAMESPACE_URL, 'effort-changes')}\n"
        "\tfromColumn: change_effort.id\n\ttoColumn: dashboard_changes.id\n")
    for t in TABLES:
        (d / "tables" / f"{t}.tmdl").write_text(_tmdl_table(t))


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


def nav_buttons(page_index):
    out = []
    for i, p in enumerate(PAGES):
        y = 190 + i * 66
        out.append(container(f"nav{page_index}{i}0000000000000", (30, y, 330, y + 56), {
            "visualType": "actionButton",
            "objects": {"icon": [{"properties": {"shapeType": lit("'blank'")}}], "fill": [{"properties": {"show": lit("false")}}],
                        "outline": [{"properties": {"show": lit("false")}}], "text": [{"properties": {"show": lit("false")}}]},
            "visualContainerObjects": {**NO_FRAME, "visualLink": [{"properties": {
                "show": lit("true"), "type": lit("'PageNavigation'"), "navigationSection": lit(f"'{p['id']}'")}}]}}, 9000 + i))
    return out


def slicer(name, box, entity, col, title, z, group):
    return container(name, box, {
        "visualType": "slicer", "query": {"queryState": {"Values": {"projections": [proj(entity, col, active=True)]}}},
        "objects": {"data": [{"properties": {"mode": lit("'Dropdown'")}}], "header": [{"properties": {"show": lit("false")}}],
                    "items": [{"properties": {"fontColor": colour(TOKENS["ink"]), "background": colour("#EEF5D3"), "textSize": lit("12D")}}],
                    "selection": [{"properties": {"selectAllCheckboxEnabled": lit("true")}}]},
        "visualContainerObjects": {**NO_FRAME, "title": [{"properties": {
            "show": lit("true"), "text": lit(f"'{title}'"), "fontColor": colour(TOKENS["lime"]), "fontSize": lit("11D"),
            "background": colour(TOKENS["ink"])}}]}}, z, {"syncGroup": {"groupName": group, "fieldChanges": True, "filterChanges": True}})


def page_brief(p):
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
                                 "Y": {"projections": [proj(C, "Hours Needed", True), proj(C, "Hours Available", True)]}},
                  "sortDefinition": {"sort": [{"field": field(C, "Hours Needed", True), "direction": "Descending"}]}},
        "objects": {"labels": [{"properties": {"show": lit("true"), "fontSize": lit("10D")}}],
                    "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}],
                    "dataPoint": [{"properties": {"fill": colour(TOKENS["lime_dark"])}, "selector": {"metadata": f"{C}.Hours Needed"}},
                                  {"properties": {"fill": colour(TOKENS["muted"])}, "selector": {"metadata": f"{C}.Hours Available"}}]}}, 1050))
    return vs


def page_capacity(p):
    P = p["panels"]
    k = kpi_boxes(5)
    C, E, L, F = "capacity_monthly", "dashboard_changes", "run_log", "change_effort"
    vs = [container(f"kpc{i}0000000000000000", k[i], card(t, m), 1000 + i)
          for i, (t, m) in enumerate([(C, "Capacity Load"), (C, "Hours Over Capacity"), (C, "FTE Gap (months)"),
                                      (E, "Ongoing Cost / yr"), (L, "Sources OK Label")])]
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
                    "columnWidth": [{"properties": {"value": lit("150D")}, "selector": {"metadata": f"{L}.run_at"}},
                                    {"properties": {"value": lit("90D")}, "selector": {"metadata": f"{L}.agency"}},
                                    {"properties": {"value": lit("480D")}, "selector": {"metadata": f"{L}.status"}},
                                    {"properties": {"value": lit("60D")}, "selector": {"metadata": f"{L}.items"}}]}}, 1040))
    return vs


ABOUT = [
    ("How this report works", 24, True, TOKENS["ink"]),
    ("Every Monday at 07:17 Sydney time, GitHub Actions runs the monitor in Docker: it reads official agency news (RSS first, news page "
     "fallback, robots.txt checked), keeps what is new and relevant, tags it and estimates its cost and effort, then commits the results "
     "to GitHub. This report reads those files over HTTPS: press Refresh to load the latest run.", 16, False, TOKENS["ink"]),
    ("Sample or live data", 18, True, TOKENS["lime_dark"]),
    ("Transform data > Edit parameters > Dataset: 'bi_export' is a synthetic year that shows every feature; 'data/live' is the real weekly "
     "monitor. Branch: 'main'.", 16, False, TOKENS["ink"]),
    ("Measures", 18, True, TOKENS["lime_dark"]),
    ("Needs action: action required and not yet done. Past target date: needs action and the stated deadline (or published + 30/60/90 days "
     "for High/Medium/Low) has passed. Cost: staff hours x loaded hourly rate + external spend. Capacity load: hours the outstanding work "
     "needs in a month / hours each role can give to regulatory work.", 16, False, TOKENS["ink"]),
    ("Limits", 18, True, TOKENS["lime_dark"]),
    ("Tags come from keyword rules and costs from stated assumptions (impact_model.py), not from legal advice or quotes. Some agency sites "
     "refuse cloud runners; the Source health table shows which ones answered.", 16, False, TOKENS["ink"]),
]


def page_about(p):
    paras = []
    for text, size, bold, col in ABOUT:
        style = {"fontSize": f"{size}pt", "color": col}
        if bold:
            style["fontWeight"] = "bold"
        paras += [{"textRuns": [{"value": text, "textStyle": style}]}, {"textRuns": [{"value": " ", "textStyle": {"fontSize": "6pt"}}]}]
    return [container("abouttext0000000000", inner(p["panels"]["text"][0], 24, 36), {
        "visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paras}}]}}, 1000)]


def build_report() -> None:
    d = REPORT / "definition"
    shutil.rmtree(REPORT, ignore_errors=True)
    (d / "pages").mkdir(parents=True)
    res = REPORT / "StaticResources"
    (res / "SharedResources" / "BaseThemes").mkdir(parents=True)
    (res / "RegisteredResources").mkdir(parents=True)
    shutil.copy(ASSETS / "Fluent2-CY26SU09.json", res / "SharedResources" / "BaseThemes")
    shutil.copy(ASSETS / "SlateLime5001.json", res / "RegisteredResources")
    (REPORT / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2))
    (d / "version.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}))
    imgs = []
    builders = [page_brief, page_capacity, page_about]
    for i, p in enumerate(PAGES):
        bg = f"bg_live_{i + 1}.png"
        background(p, res / "RegisteredResources" / bg)
        imgs.append({"name": bg, "path": bg, "type": "Image"})
        pd_ = d / "pages" / p["id"]
        (pd_ / "visuals").mkdir(parents=True)
        (pd_ / "page.json").write_text(json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": p["id"], "displayName": p["name"], "displayOption": "FitToPage", "height": H, "width": W,
            "objects": {"background": [{"properties": {"image": {"image": {
                "name": lit(f"'{bg}'"), "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": bg}}},
                "scaling": lit("'Fit'")}}, "transparency": lit("0D")}}]}}))
        for v in builders[i](p) + nav_buttons(i):
            (pd_ / "visuals" / v["name"]).mkdir()
            (pd_ / "visuals" / v["name"] / "visual.json").write_text(json.dumps(v))
    rv = {"visual": "2.13.0", "report": "3.4.0", "page": "2.3.1"}
    (d / "report.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "Fluent2-CY26SU09", "reportVersionAtImport": rv, "type": "SharedResources"},
                            "customTheme": {"name": "SlateLime5001.json", "reportVersionAtImport": rv, "type": "RegisteredResources"}},
        "objects": {"outspacePane": [{"properties": {"expanded": lit("false")}}]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "Fluent2-CY26SU09", "path": "BaseThemes/Fluent2-CY26SU09.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": imgs + [{"name": "SlateLime5001.json", "path": "SlateLime5001.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True, "useEnhancedTooltips": True,
                     "useDefaultAggregateDisplayName": True}}))
    (d / "pages" / "pages.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
        "pageOrder": [p["id"] for p in PAGES], "activePageName": PAGES[0]["id"]}))


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
