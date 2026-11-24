"""Render the Power BI report (PBIR pages + visuals) to one HTML page, so it can be checked and shared without Power BI.

    python powerbi/render_preview.py [--dataset bi_export|data/live] [--out preview/report.html]

The script reads the report exactly as Power BI does: page sizes and backgrounds from page.json, every visual's
position, type, fields, filters, sort and colours from visual.json, and the data from the same CSVs the semantic
model loads. Each measure used by the report is re-implemented in pandas next to its DAX (see MEASURES), and
tests/test_report_preview.py checks the two stay in step. It draws a faithful static view: no cross-filtering.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import math
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = HERE / "RegulatoryChangeMonitor.Report"
PAGES = REPORT / "definition" / "pages"
RES = REPORT / "StaticResources" / "RegisteredResources"
THEME = json.loads((RES / "SlateLime5001.json").read_text())
COLOURS = THEME["dataColors"]
INK, LIME, SLATE, MUTED = "#1f2933", "#b6d94c", "#46586b", "#6b7f94"
FONT = "'Segoe UI', 'Segoe UI Web (West European)', -apple-system, 'Helvetica Neue', Arial, sans-serif"


# ---------------------------------------------------------------- data (same CSVs and calculated objects as the model)
TOPIC_DEPARTMENT = [("AML/CTF", "Compliance & AML"), ("Sanctions", "Compliance & AML"), ("Trust Accounts", "Accounts & Trust"),
                    ("Tax", "Accounts & Trust"), ("Payroll", "HR & Payroll"), ("Payroll", "Accounts & Trust"),
                    ("Superannuation", "HR & Payroll"), ("Superannuation", "Accounts & Trust"), ("Employment", "HR & Payroll"),
                    ("Property", "Property"), ("Privacy & Data", "Privacy & IT")]


class Data:
    def __init__(self, dataset: str):
        base = ROOT / dataset

        def read(name, dates=()):
            p = base / name
            if not p.exists():
                return pd.DataFrame()
            df = pd.read_csv(p)
            for c in dates:
                df[c] = pd.to_datetime(df[c], errors="coerce", utc=(c == "run_at")).dt.tz_localize(None) if c == "run_at" \
                    else pd.to_datetime(df[c], errors="coerce")
            return df

        self.dash = read("dashboard_changes.csv", ("published", "deadline", "target_date", "as_of", "first_seen"))
        # "today" for the report is the date of the data, not the date the file is opened (measure As Of Date)
        self.as_of = self.dash["as_of"].max().normalize()
        c = read("changes.csv", ("published", "deadline"))
        c["Days To Deadline"] = (c["deadline"] - self.as_of).dt.days
        c["Deadline Bucket"] = c["deadline"].map(
            lambda d: "No fixed date" if pd.isna(d) else "Overdue" if d < self.as_of else
            "Due in 30 days" if d <= self.as_of + pd.Timedelta(days=30) else "Later")
        dd = read("dim_date.csv", ("date",)).set_index("date")
        c["year_month"] = c["published"].map(dd["year_month"])
        c["year"] = c["published"].map(dd["year"])
        self.changes = c
        self.topics = read("change_topics.csv")
        td = pd.DataFrame(TOPIC_DEPARTMENT, columns=["topic", "department"])
        self.dept = self.topics.merge(td, on="topic")
        self.effort = read("change_effort.csv")
        self.cap = read("capacity_monthly.csv", ("month_start",))
        self.log = Data._live_log()
        self.snap = read("weekly_snapshot.csv", ("run_date",))
        self.qc = read("quality_checks.csv", ("run_date",))
        if len(self.qc):
            self.qc["Latest Load"] = (self.qc["run_date"] == self.qc["run_date"].max()).map({True: "Yes", False: "No"})
            for c in ("blocking", "passed"):
                self.qc[c] = self.qc[c].astype(str).str.capitalize()
        if self.log.empty:
            self.log = pd.DataFrame({"run_at": pd.Series(dtype="datetime64[ns]"), "agency": [], "feed": [], "status": [], "items": []})

    @staticmethod
    def _live_log():
        p = ROOT / "data" / "live" / "run_log.csv"
        if not p.exists():
            return pd.DataFrame()
        df = pd.read_csv(p)
        df["run_at"] = pd.to_datetime(df["run_at"], utc=True).dt.tz_localize(None)
        return df

    # ids of changes linked to a value of a related column (bridge tables filter changes both ways)
    def link(self, entity: str, col: str) -> pd.DataFrame:
        if entity == "changes" or (entity == "dim_date" and col in ("year_month", "year")):
            return self.changes[["id", col]].rename(columns={col: "v"})
        if (entity, col) in (("change_topics", "topic"), ("dim_topic", "topic")):
            return self.topics[["id", "topic"]].rename(columns={"topic": "v"})
        if entity in ("dim_department", "topic_department") and col == "department":
            return self.dept[["id", "department"]].drop_duplicates().rename(columns={"department": "v"})
        raise KeyError(f"{entity}.{col}")


# ---------------------------------------------------------------- measures (DAX in build_pbip.py; same logic here)
def _open(c):
    return c[(c["action_req"] == 1) & (c["status"] != "Actioned")]


def changes_measures(D: Data):
    t = D.as_of
    return {
        "Total Changes": lambda c: len(c),
        "High Impact": lambda c: int((c["impact"] == "High").sum()),
        "Open Actions": lambda c: len(_open(c)),
        "Overdue Actions": lambda c: int((_open(c)["deadline"] < t).sum()),
        "Due In 30 Days": lambda c: int(_open(c)["deadline"].between(t, t + pd.Timedelta(days=30)).sum()),
        "Action Rate": lambda c: len(_open(c)) / len(c) if len(c) else None,
        "Heat Color": lambda c: None if not len(c) else "#F1F7DA" if len(c) <= 10 else "#DDEBA6" if len(c) <= 25
        else "#C8E070" if len(c) <= 45 else "#A9CF3A",
        "Deadline Color": lambda c: None if c["Days To Deadline"].isna().all() else (
            lambda d: "#C0392B" if d < 0 else "#D98E04" if d <= 30 else INK)(c["Days To Deadline"].min()),
    }


def dash_measures(D: Data):
    a = D.as_of
    out = lambda d: d[d["work_status"] == "Outstanding"]
    m = {
        "Changes": lambda d: len(d),
        "New This Week": lambda d: int((d["first_seen"] > a - pd.Timedelta(days=7)).sum()),
        "Needs Action": lambda d: len(out(d)),
        "Past Target Date": lambda d: int((out(d)["days_left"] < 0).sum()),
        "One-off Cost": lambda d: d["total_one_off_cost"].sum(),
        "Staff Time Cost": lambda d: d["internal_one_off_cost"].sum(),
        "External Cost": lambda d: d["external_one_off"].sum(),
        "Ongoing Cost / yr": lambda d: d["total_ongoing_cost_yr"].sum(),
        "Backlog Hours": lambda d: d["outstanding_hours"].sum(),
        "Days Left Colour": lambda d: (lambda x: "#C0392B" if x < 0 else "#D98C00" if x < 14 else INK)(d["days_left"].max()),
    }
    m["Takeaway"] = lambda d: (f"The changes on file cost about ${m['One-off Cost'](d):,.0f} once and ${m['Ongoing Cost / yr'](d):,.0f} a year. "
                               f"{m['Past Target Date'](d)} are past their target date and the backlog is {m['Backlog Hours'](d):,.0f} staff hours.")
    return m


def cap_measures():
    need = lambda c: c["hours_required"].sum()
    avail = lambda c: c["hours_available"].sum()
    load = lambda c: need(c) / avail(c) if avail(c) else None
    return {
        "Hours Needed": need, "Hours Available": avail, "Capacity Load": load,
        "Hours Available / Month": lambda c: c.groupby("month_start")["hours_available"].sum().mean() if len(c) else None,
        "Capacity Takeaway": lambda c: (lambda pm: (lambda g: f"Money is manageable, hours are not: {pm:%b %Y} needs {need(g):,.0f} hours against "
                                                    f"{avail(g):,.0f} available. Short-term help for that month covers it.")
                                        (c[c["month_start"] == pm]))(max(c.groupby("month_start"), key=lambda kv: load(kv[1]) or 0)[0]),
        "Hours Over Capacity": lambda c: c["hours_over_capacity"].sum(),
        "FTE Gap (months)": lambda c: c["hours_over_capacity"].sum() / 152,
        "Peak Month Load": lambda c: max((load(g) or 0) for _, g in c.groupby("month_start")) if len(c) else None,
        "Load Colour": lambda c: (lambda l: None if l is None else "#E8A29A" if l > 1 else "#F3D27A" if l > 0.8 else "#D9EC9A")(load(c)),
    }


def log_measures():
    def latest(r):
        return r[r["run_at"].dt.normalize() == r["run_at"].max().normalize()] if len(r) else r
    checked = lambda r: len(latest(r))
    ok = lambda r: int(latest(r)["status"].astype(str).str[:2].eq("ok").sum()) if len(r) else 0
    return {"Sources Checked": checked, "Sources OK": ok,
            "Sources OK Label": lambda r: "n/a (sample)" if checked(r) == 0 else f"{ok(r)} / {checked(r)}"}


def snap_measures():
    def at(df, d, col):
        return df.loc[df["run_date"] == d, col].sum()
    last = lambda df: df["run_date"].max() if len(df) else None

    def vs4(df_all, df):
        d = last(df)
        prev = df_all[df_all["run_date"] <= d - pd.Timedelta(days=28)]["run_date"].max() if d is not None else None
        return None if prev is None or pd.isna(prev) else at(df, d, "backlog_hours") - at(df_all, prev, "backlog_hours")

    m = {
        "Weekly Runs": lambda df: len(df),
        "Changes On File (run)": lambda df: at(df, last(df), "changes_on_file") if len(df) else None,
        "New Changes (run)": lambda df: df["new_this_run"].sum(),
        "Needs Action (run)": lambda df: at(df, last(df), "needs_action") if len(df) else None,
        "Past Target (run)": lambda df: at(df, last(df), "past_target_date") if len(df) else None,
        "Backlog Hours (run)": lambda df: at(df, last(df), "backlog_hours") if len(df) else None,
    }
    return m, vs4


FORMATS = {"Backlog vs 4 Weeks": "+", "Action Rate": "0%", "Capacity Load": "0%", "Peak Month Load": "0%", "FTE Gap (months)": "0.0", "One-off Cost": "$", "Staff Time Cost": "$",
           "External Cost": "$", "Ongoing Cost / yr": "$", "total_one_off_cost": "$"}


def fmt(v, name="", short=False):
    if v is None or v is pd.NaT or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, pd.Timestamp):
        return f"{v.day}/{v.month}/{v.year}"
    f = FORMATS.get(name, "")
    if f == "0%":
        return f"{v:.0%}" if not short else f"{v * 100:.1f}%"
    if f == "0.0":
        return f"{v:.1f}"
    if f == "+":
        return f"{v:+,.0f}"
    pre = "$" if f == "$" else ""
    if short and abs(v) >= 1000:
        return f"{pre}{v / 1000:.0f}K" if abs(v) >= 10000 else f"{pre}{v / 1000:.1f}K"
    return f"{pre}{v:,.0f}" if float(v).is_integer() or pre or abs(v) >= 10 else f"{v:,.1f}"


# ---------------------------------------------------------------- report reading helpers
def lit(o, default=None):
    try:
        v = o["expr"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return default
    if v in ("true", "false"):
        return v == "true"
    if v.endswith("D") or v.endswith("L"):
        try:
            return float(v[:-1])
        except ValueError:
            pass
    return v.strip("'")


def prop(objs, name, key, default=None):
    for o in (objs or {}).get(name, []):
        if "selector" in o:
            continue
        if key in o.get("properties", {}):
            p = o["properties"][key]
            if isinstance(p, dict) and "solid" in p:
                return lit(p["solid"]["color"], default)
            return lit(p, default)
    return default


def field_ref(f):
    for k in ("Measure", "Column"):
        if k in f:
            return k, f[k]["Expression"]["SourceRef"].get("Entity"), f[k]["Property"]
    if "Aggregation" in f:
        c = f["Aggregation"]["Expression"]["Column"]
        return "Column", c["Expression"]["SourceRef"]["Entity"], c["Property"]
    raise ValueError(f)


def esc(s):
    return html.escape(str(s))


# ---------------------------------------------------------------- filters
def _cond(df, cond, alias):
    if "And" in cond:
        return _cond(df, cond["And"]["Left"], alias) & _cond(df, cond["And"]["Right"], alias)
    if "Or" in cond:
        return _cond(df, cond["Or"]["Left"], alias) | _cond(df, cond["Or"]["Right"], alias)
    if "Not" in cond:
        return ~_cond(df, cond["Not"]["Expression"], alias)
    if "In" in cond:
        col = cond["In"]["Expressions"][0]["Column"]["Property"]
        vals = [lit({"expr": v[0]}) for v in cond["In"]["Values"]]
        return df[col].isin(vals)
    if "Comparison" in cond:
        c = cond["Comparison"]
        col = c["Left"]["Column"]["Property"]
        right = c["Right"]
        if "Literal" in right:
            v = lit({"expr": right})
            if v == "null":
                s = df[col].isna()
                return s if c["ComparisonKind"] == 0 else ~s
            if isinstance(v, str) and v.startswith("datetime"):
                v = pd.Timestamp(v[8:].strip("'"))
        else:
            v = None
        k = c["ComparisonKind"]
        s = df[col]
        if v is None:
            return s.isna() if k == 0 else s.notna()
        return {0: s == v, 1: s > v, 2: s >= v, 3: s < v, 4: s <= v}[k].fillna(False)
    raise ValueError(cond)


def apply_filters(df, filters, entity):
    for f in filters:
        flt = f.get("filter")
        if not flt or f.get("field") and field_ref(f["field"])[1] != entity:
            continue
        for w in flt.get("Where", []):
            df = df[_cond(df, w["Condition"], None).values]
    return df


# ---------------------------------------------------------------- query engine
class Engine:
    def __init__(self, D: Data):
        self.D = D
        sm, vs4 = snap_measures()
        sm["Backlog vs 4 Weeks"] = lambda df: vs4(D.snap, df)
        sm["Trend Takeaway"] = lambda df: "No weekly history yet: it builds up from the first Databricks load." if not len(df) else (
            lambda d, ch: f"Backlog {sm['Backlog Hours (run)'](df):,.0f} hours, {'up' if (ch or 0) >= 0 else 'down'} {abs(ch or 0):,.0f} in four weeks; "
                          f"{sm['Past Target (run)'](df):.0f} changes past their target date "
                          f"({D.snap.loc[D.snap['run_date'] == D.snap[D.snap['run_date'] <= d - pd.Timedelta(days=28)]['run_date'].max(), 'past_target_date'].sum():.0f} four weeks earlier).")(
            df["run_date"].max(), vs4(D.snap, df))
        qm = {"Checks Passed Label": lambda q: "n/a" if not len(q) else
              (lambda l: f"{(l['passed'] == 'True').sum()} / {len(l)}")(q[q["run_date"] == q["run_date"].max()]),
              "Check Colour": lambda q: "#5F7A1A" if (q["passed"] == "True").all() else "#C0392B" if (q["blocking"] == "True").any() else "#D98C00"}
        self.M = {"changes": changes_measures(D), "dashboard_changes": dash_measures(D), "capacity_monthly": cap_measures(),
                  "change_effort": {}, "run_log": log_measures(), "weekly_snapshot": sm, "quality_checks": qm}

    def frame(self, entity, page_filters, vis_filters):
        D = self.D
        self.dept_topics = None
        if entity in ("changes", "change_topics", "dim_date", "dim_department", "dim_topic"):
            c = D.changes
            for f in page_filters + vis_filters:
                ent = field_ref(f["field"])[1]
                if ent == "dim_department":
                    vals = [lit({"expr": v[0]}) for w in f["filter"]["Where"] for v in w["Condition"]["In"]["Values"]]
                    self.dept_topics = set(D.dept[D.dept["department"].isin(vals)]["topic"])
                    c = c[c["id"].isin(D.dept[D.dept["department"].isin(vals)]["id"])]
                elif ent == "changes":
                    c = apply_filters(c, [f], "changes")
            return "changes", c
        if entity == "dashboard_changes":
            return entity, apply_filters(D.dash, vis_filters, entity)
        if entity == "change_effort":
            return entity, D.effort
        if entity == "capacity_monthly":
            return entity, D.cap
        if entity == "run_log":
            return entity, D.log
        if entity == "weekly_snapshot":
            return entity, D.snap
        if entity == "quality_checks":
            return entity, apply_filters(D.qc, vis_filters, entity) if len(D.qc) else D.qc
        raise KeyError(entity)

    def measure(self, fam, name, df):
        if fam == "change_effort" or name == "Outstanding Role Hours":
            out = self.D.dash.loc[self.D.dash["work_status"] == "Outstanding", "id"]
            return df[df["id"].isin(out)]["one_off_hours"].sum()
        return self.M[fam][name](df)

    def groups(self, fam, df, entity, col):
        """(value, subset) pairs for a category column, following the model's relationships."""
        if fam == "changes" and entity != "changes" or (fam == "changes" and col in ("year_month", "year")):
            L = self.D.link(entity, col)
            L = L[L["id"].isin(df["id"])]
            if entity in ("change_topics", "dim_topic") and getattr(self, "dept_topics", None):
                L = L[L["v"].isin(self.dept_topics)]
            return [(v, df[df["id"].isin(g["id"])]) for v, g in L.groupby("v", sort=False)]
        return list(df.groupby(col, sort=False))


# ---------------------------------------------------------------- drawing
def svg(w, h, body):
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="font-family:{FONT}">{body}</svg>'


def text(x, y, s, size=11, fill=INK, anchor="start", weight=400, extra=""):
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" {extra}>{esc(s)}</text>'


def nice_max(v):
    if v <= 0:
        return 1
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * e:
            return m * e
    return 10 * e


def legend(items, w, y):
    """Bottom legend, centred, Power BI style (circle markers)."""
    widths = [len(s) * 6.2 + 22 for s, _ in items]
    x = max(4, (w - sum(widths)) / 2)
    out = ""
    for (s, c), wd in zip(items, widths):
        out += f'<circle cx="{x + 5}" cy="{y - 4}" r="4.5" fill="{c}"/>' + text(x + 13, y, s, 11, "#605e5c")
        x += wd
    return out


def series_colour(objs, value, i):
    for o in (objs or {}).get("dataPoint", []):
        sel = o.get("selector", {})
        for d in sel.get("data", []):
            sc = d.get("scopeId", {}).get("Comparison")
            if sc and lit({"expr": sc["Right"]}) == value:
                return lit(o["properties"]["fill"]["solid"]["color"])
        if sel.get("metadata", "").split(".")[-1] == value:
            return lit(o["properties"]["fill"]["solid"]["color"])
    if any("selector" not in o for o in (objs or {}).get("dataPoint", [])):
        c = prop(objs, "dataPoint", "fill")
        if c:
            return c
    return COLOURS[i % len(COLOURS)]


def draw_column(w, h, cats, series, objs, stacked=True, horizontal=False, labels=None, names=None, line=None):
    """cats: list of labels; series: list of (name, values, colour). Clustered when stacked=False."""
    show_labels = labels if labels is not None else (prop(objs, "labels", "show", False) or True)
    leg = len(series) > 1 or line is not None
    lh = 24 if leg else 0
    body = ""
    n = max(1, len(cats))
    if horizontal:
        lw = min(170, max(len(str(c)) for c in cats) * 6.6 + 12) if cats else 40
        top, bot = 6 + (lh if leg else 0), h - 6
        x0, x1 = lw, w - 46
        tot = [sum(s[1][i] or 0 for s in series) if stacked else max(s[1][i] or 0 for s in series) for i in range(len(cats))]
        mx = nice_max(max(tot + [0]))
        band = (bot - top) / n
        bh = band * 0.62
        for i, c in enumerate(cats):
            y = top + band * i + (band - bh) / 2
            body += text(lw - 6, y + bh / 2 + 4, c, 11, "#605e5c", "end")
            acc = 0
            for k, (sn, vals, col) in enumerate(series):
                v = vals[i] or 0
                if stacked:
                    bw = (x1 - x0) * v / mx
                    body += f'<rect x="{x0 + (x1 - x0) * acc / mx:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{col[i] if isinstance(col, list) else col}"><title>{esc(c)} · {esc(sn)}: {fmt(v, sn)}</title></rect>'
                    if bw > 34 and show_labels:
                        body += text(x0 + (x1 - x0) * (acc + v / 2) / mx, y + bh / 2 + 4, fmt(v, sn, True), 10, "#fff" if k == 0 else INK, "middle")
                    acc += v
                else:
                    sh = bh / len(series)
                    bw = (x1 - x0) * v / mx
                    body += f'<rect x="{x0}" y="{y + sh * k:.1f}" width="{bw:.1f}" height="{sh - 1:.1f}" fill="{col}"><title>{esc(c)} · {esc(sn)}: {fmt(v, sn)}</title></rect>'
                    if show_labels:
                        body += text(x0 + bw + 4, y + sh * k + sh / 2 + 3.5, fmt(v, sn, True), 9.5, "#605e5c")
            if stacked and show_labels and len(series) == 1:
                pass
            if stacked and len(series) > 1 and show_labels:
                body += text(x0 + (x1 - x0) * acc / mx + 4, y + bh / 2 + 4, fmt(acc, series[0][0], True), 10, INK, weight=600)
            elif stacked and show_labels:
                v = series[0][1][i] or 0
                if (x1 - x0) * v / mx <= 34:
                    body += text(x0 + (x1 - x0) * v / mx + 4, y + bh / 2 + 4, fmt(v, series[0][0], True), 10, INK)
        if leg:
            body += legend([(s[0], s[2]) for s in series], w, 14)
        return svg(w, h, body)
    # vertical
    rot = n > 8 and max((len(str(c)) for c in cats), default=0) > 4
    xb = 44 if rot else 24
    top, bot = 14, h - lh - xb
    x0, x1 = 8 + (22 if rot else 0), w - 8 - (30 if line else 0)
    tot = [sum(s[1][i] or 0 for s in series) if stacked else max(s[1][i] or 0 for s in series) for i in range(len(cats))]
    mx = nice_max(max(tot + [0]) * 1.08)
    band = (x1 - x0) / n
    bw = band * 0.64
    for i, c in enumerate(cats):
        x = x0 + band * i + (band - bw) / 2
        acc = 0
        for k, (sn, vals, col) in enumerate(series):
            v = vals[i] or 0
            if stacked:
                bh = (bot - top) * v / mx
                y = bot - (bot - top) * (acc + v) / mx
                body += f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{col[i] if isinstance(col, list) else col}"><title>{esc(c)} · {esc(sn)}: {fmt(v, sn)}</title></rect>'
                acc += v
            else:
                sw = bw / len(series)
                bh = (bot - top) * v / mx
                body += f'<rect x="{x + sw * k:.1f}" y="{bot - bh:.1f}" width="{sw - 1:.1f}" height="{bh:.1f}" fill="{col}"/>'
        if show_labels and (len(series) == 1 or stacked) and n <= 16:
            body += text(x + bw / 2, bot - (bot - top) * acc / mx - 4, fmt(acc, series[0][0], True), 10.5, "#605e5c", "middle")
        lab = str(c)
        if n > 16 and i % thin(n, x1 - x0) and i != n - 1:
            continue
        if rot:
            body += text(x + bw / 2, bot + 12, lab, 10.5, "#605e5c", "end", extra=f'transform="rotate(-40 {x + bw / 2:.1f} {bot + 12:.1f})"')
        else:
            body += text(x + bw / 2, bot + 15, lab, 10.5, "#605e5c", "middle")
    if line:
        lname, lvals, lcol = line
        lmx = max([v for v in lvals if v is not None] + [0.0001]) * 1.25
        pts = [(x0 + band * i + band / 2, bot - (bot - top) * (v or 0) / lmx) for i, v in enumerate(lvals)]
        body += f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" stroke="{lcol}" stroke-width="3"/>'
        for j, ((a, b), v) in enumerate(zip(pts, lvals)):
            body += f'<circle cx="{a:.1f}" cy="{b:.1f}" r="{4 if n <= 16 else 2.5}" fill="{lcol}"/>'
            if n > 16 and j != n - 1:
                continue
            body += f'<rect x="{a - 19:.1f}" y="{b - 22:.1f}" width="38" height="15" rx="2" fill="#fff" fill-opacity=".85"/>' + text(a, b - 11, fmt(v, lname, True), 10, INK, "middle")
    if leg:
        items = [(s[0], s[2]) for s in series] + ([(line[0], line[2])] if line else [])
        body += legend(items, w, h - 6)
    return svg(w, h, body)


def thin(n, room, each=34):
    """Show every k-th category label so dense axes stay readable."""
    return max(1, math.ceil(n * each / max(room, 1)))


def draw_lines(w, h, cats, series):
    top, bot, x0, x1 = 12, h - 34, 40, w - 14
    vals = [v or 0 for _, vs, _ in series for v in vs]
    mx = nice_max(max(vals + [1]) * 1.1)
    n = max(1, len(cats))
    xs = [x0 + (x1 - x0) * (i + 0.5) / n for i in range(n)]
    body = ""
    for k in range(5):
        y = bot - (bot - top) * k / 4
        body += f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e1e6ea"/>' + text(x0 - 6, y + 4, fmt(mx * k / 4, "", True), 10, "#8a96a3", "end")
    for name, vs, col in series:
        pts = [(x, bot - (bot - top) * (v or 0) / mx) for x, v in zip(xs, vs)]
        body += f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" stroke="{col}" stroke-width="3"/>'
        for (a, b), v, c in zip(pts, vs, cats):
            body += f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3" fill="{col}"><title>{esc(c)}: {fmt(v, name)}</title></circle>'
        if pts:
            body += text(pts[-1][0], pts[-1][1] - 8, fmt(vs[-1], name), 11, INK, "end", 700)
    step = thin(n, x1 - x0, 62)
    for i, c in enumerate(cats):
        if i % step == 0 and (n - 1 - i) >= step or i == n - 1:
            body += text(xs[i], bot + 16, c, 10, "#605e5c", "middle")
    return svg(w, h, body)


def draw_donut(w, h, cats, vals, cols):
    tot = sum(vals) or 1
    lh = 26
    cx, cy = w / 2, (h - lh) / 2 + 4
    r = min(w * 0.36, (h - lh) / 2 - 22)
    ri = r * 0.58
    a = -math.pi / 2
    body = ""
    for c, v, col in zip(cats, vals, cols):
        b = a + 2 * math.pi * v / tot
        large = 1 if b - a > math.pi else 0
        p = lambda ang, rad: (cx + rad * math.cos(ang), cy + rad * math.sin(ang))
        (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p(a, r), p(b, r), p(b, ri), p(a, ri)
        body += (f'<path d="M{x1:.1f},{y1:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} L{x3:.1f},{y3:.1f} '
                 f'A{ri:.1f},{ri:.1f} 0 {large} 0 {x4:.1f},{y4:.1f}Z" fill="{col}"><title>{esc(c)}: {v}</title></path>')
        m = (a + b) / 2
        lx, ly = p(m, r + 16)
        body += text(lx, ly + 4, f"{v} ({v / tot:.0%})", 11, "#605e5c", "start" if math.cos(m) > 0.1 else "end" if math.cos(m) < -0.1 else "middle")
        a = b
    body += legend(list(zip(cats, cols)), w, h - 6)
    return svg(w, h, body)


def squarify(items, x, y, w, h):
    """Squarified treemap layout. items: [(label, value)] sorted desc. Returns [(label, value, x, y, w, h)]."""
    out, items = [], [i for i in items if i[1] > 0]
    total = sum(v for _, v in items)
    if not items or w <= 0 or h <= 0:
        return out
    scale = w * h / total
    rects = [(l, v * scale, v) for l, v in items]

    def worst(row, side):
        s = sum(r[1] for r in row)
        return max(max(side * side * r[1] / s / s, s * s / side / side / r[1]) for r in row)

    while rects:
        side = min(w, h)
        row = [rects.pop(0)]
        while rects and worst(row + [rects[0]], side) <= worst(row, side):
            row.append(rects.pop(0))
        s = sum(r[1] for r in row)
        if w >= h:
            cw = s / h
            yy = y
            for l, a, v in row:
                out.append((l, v, x, yy, cw, a / cw))
                yy += a / cw
            x, w = x + cw, w - cw
        else:
            ch = s / w
            xx = x
            for l, a, v in row:
                out.append((l, v, xx, y, a / ch, ch))
                xx += a / ch
            y, h = y + ch, h - ch
    return out


def draw_treemap(w, h, items):
    body = ""
    for i, (l, v, x, y, rw, rh) in enumerate(squarify(sorted(items, key=lambda t: -t[1]), 0, 0, w, h - 24)):
        col = COLOURS[i % len(COLOURS)]
        light = col.lower() in ("#b6d94c", "#c3ccd6", "#d9ec9a", "#9fb0c0", "#e0e6ec", "#8aa63a")
        body += f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{max(0, rw - 2):.1f}" height="{max(0, rh - 2):.1f}" fill="{col}"><title>{esc(l)}: {v}</title></rect>'
        if rw > 46 and rh > 22:
            body += text(x + 6, y + 16, l, 11.5, INK if light else "#fff", weight=600)
            body += text(x + 6, y + 31, v, 11, INK if light else "#e6eaee")
    body += legend([(l, COLOURS[i % len(COLOURS)]) for i, (l, _) in enumerate(sorted(items, key=lambda t: -t[1])[:5])], w, h - 6)
    return svg(w, h, body)


def draw_table(w, h, headers, rows, colours=None, widths=None, font=12, zebra=True):
    widths = widths or [None] * len(headers)
    fixed = sum(x for x in widths if x)
    free = max(60, (w - fixed) / max(1, sum(1 for x in widths if not x)))
    ws = [x if x else free for x in widths]
    scale = min(1.0, w / sum(ws)) if sum(ws) > w else w / sum(ws)
    ws = [x * scale for x in ws]
    th = "".join(f'<th style="width:{x:.0f}px">{esc(hd)}</th>' for hd, x in zip(headers, ws))
    tr = ""
    for i, r in enumerate(rows):
        tds = ""
        for j, v in enumerate(r):
            st = ""
            if colours and colours[i] and colours[i][j]:
                k, c = colours[i][j]
                st = f'{k}:{c};' + ("font-weight:600;" if k == "color" else "")
            tds += f'<td style="{st}">{esc(v)}</td>'
        tr += f"<tr>{tds}</tr>"
    return (f'<div class="tbl" style="height:{h}px;font-size:{font}px"><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{tr}</tbody></table></div>')


# ---------------------------------------------------------------- visual dispatch
class Renderer:
    def __init__(self, dataset):
        self.D = Data(dataset)
        self.E = Engine(self.D)
        self.pages = []

    def roles(self, vi):
        q = vi.get("query", {}).get("queryState", {})
        return {k: [(field_ref(p["field"]), p.get("displayName")) for p in r["projections"]] for k, r in q.items()}

    def sort_def(self, vi):
        s = vi.get("query", {}).get("sortDefinition", {}).get("sort", [])
        return [(field_ref(x["field"]), x.get("direction", "Ascending")) for x in s]

    def visual(self, v, page_filters):
        vi = v["visual"]
        t = vi["visualType"]
        pos = v["position"]
        w, h = int(pos["width"]), int(pos["height"])
        objs = vi.get("objects", {})
        vf = v.get("filterConfig", {}).get("filters", [])
        R = self.roles(vi)
        style = f'left:{pos["x"]}px;top:{pos["y"]}px;width:{w}px;height:{h}px;z-index:{int(pos.get("z", 0)) // 10}'
        if t == "actionButton":
            link = vi.get("visualContainerObjects", {}).get("visualLink", [{}])[0].get("properties", {})
            target = lit(link.get("navigationSection", {}), "")
            return f'<a class="v nav" href="#{esc(target)}" data-go="{esc(target)}" style="{style}" aria-label="Go to page"></a>' if target else ""
        if t == "slicer":
            title = lit(vi.get("visualContainerObjects", {}).get("title", [{}])[0].get("properties", {}).get("text", {}), "")
            return (f'<div class="v slicer" style="{style}"><div class="st">{esc(title)}</div>'
                    f'<div class="sb">All<span>&#9662;</span></div></div>')
        if t == "textbox":
            paras = ""
            for p in objs["general"][0]["properties"]["paragraphs"]:
                runs = "".join(
                    f'<span style="font-size:{r.get("textStyle", {}).get("fontSize", "12pt")};font-weight:{r.get("textStyle", {}).get("fontWeight", "normal")};color:{r.get("textStyle", {}).get("color", INK)}">{esc(r["value"])}</span>'
                    for r in p["textRuns"])
                paras += f"<p>{runs}</p>"
            return f'<div class="v textbox" style="{style}">{paras}</div>'

        # measure helpers -------------------------------------------------
        def frame_for(entity):
            return self.E.frame(entity, page_filters, vf)

        if t == "cardVisual":
            (kind, ent, name), _ = R["Data"][0]
            fam, df = frame_for(ent)
            val = self.E.measure(fam, name, df)
            size = prop(objs, "value", "fontSize", 30)
            col = prop(objs, "value", "fontColor", LIME)
            bg = vi.get("visualContainerObjects", {}).get("background", [{}])[0].get("properties", {})
            bgc = lit(bg.get("color", {}).get("solid", {}).get("color", {})) if lit(bg.get("show", {})) else None
            if isinstance(val, str) and len(val) > 40:   # sentence card (takeaway)
                return f'<div class="v card txt" style="{style};font-size:{size}px;color:{col};{f"background:{bgc};" if bgc else ""}">{esc(val)}</div>'
            return f'<div class="v card" style="{style};font-size:{size}px;color:{col}"><b>{esc(fmt(val, name))}</b></div>'

        if t in ("columnChart", "barChart", "clusteredBarChart", "lineClusteredColumnComboChart", "donutChart", "treemap", "lineChart"):
            cat_key = "Category" if "Category" in R else "Group"
            (_, cent, ccol), _ = R[cat_key][0]
            ys = R.get("Y") or R.get("Values")
            fam_ent = ys[0][0][1]
            fam, df = frame_for(fam_ent if fam_ent != "change_effort" else "change_effort")
            if fam == "changes" and cent not in ("changes",) and cent in ("change_topics", "dim_date", "dim_department", "dim_topic"):
                pass
            groups = self.E.groups(fam, df, cent, ccol)
            # values per Y measure
            cats = [g[0] for g in groups]
            series_role = R.get("Series")
            if series_role:
                (_, sent, scol), _ = series_role[0]
                ORD = {"impact": ["High", "Medium", "Low"], "Deadline Bucket": ["Overdue", "Due in 30 days", "Later", "No fixed date"]}
                svals = [s for s in ORD[scol] if s in set(df[scol])] if scol in ORD else sorted(df[scol].dropna().unique())
                mname = ys[0][0][2]
                data = {s: [self.E.measure(fam, mname, g[g[scol] == s]) for _, g in groups] for s in svals}
                order_val = [sum(data[s][i] or 0 for s in svals) for i in range(len(cats))]
            else:
                data = {y[0][2]: [self.E.measure(fam, y[0][2], g) for _, g in groups] for y in ys}
                order_val = data[ys[0][0][2]]
            # sort: explicit sortDefinition, else dates/months ascending, else by first measure descending
            sd = self.sort_def(vi)
            idx = list(range(len(cats)))
            if sd:
                (k, e, n), d = sd[0]
                key = (lambda i: order_val[i] or 0) if k == "Measure" else (lambda i: cats[i])
                idx.sort(key=key, reverse=d == "Descending")
            elif ccol in ("year_month", "month_start", "target_date", "run_date") or ccol == "Deadline Bucket":
                order = ["Overdue", "Due in 30 days", "Later", "No fixed date"]
                idx.sort(key=lambda i: order.index(cats[i]) if ccol == "Deadline Bucket" else cats[i])
            else:
                idx.sort(key=lambda i: -(order_val[i] or 0))
            cats = [cats[i] for i in idx]
            data = {k: [v[i] for i in idx] for k, v in data.items()}
            if ccol == "target_date":   # Power BI date axis: hierarchy collapsed to month in the visual
                lab = [c.strftime("%b %y") for c in cats]
                agg = {}
                for l, v in zip(lab, data[list(data)[0]]):
                    agg[l] = agg.get(l, 0) + (v or 0)
                cats, data = list(agg), {list(data)[0]: list(agg.values())}
            elif ccol == "month_start":
                cats = [c.strftime("%b %Y") for c in cats]
            elif ccol == "run_date":
                cats = [c.strftime("%-d %b %y") for c in cats]
            if t == "donutChart":
                name = list(data)[0]
                cols = [series_colour(objs, c, i) for i, c in enumerate(cats)]
                order = [i for i, c in sorted(enumerate(cats), key=lambda p: ["High", "Medium", "Low"].index(p[1]) if p[1] in ("High", "Medium", "Low") else p[0])]
                return f'<div class="v" style="{style}">{draw_donut(w, h, [cats[i] for i in order], [data[name][i] for i in order], [cols[i] for i in order])}</div>'
            if t == "treemap":
                name = list(data)[0]
                return f'<div class="v" style="{style}">{draw_treemap(w, h, list(zip(cats, data[name])))}</div>'
            line = None
            if t == "lineChart":
                name = list(data)[0]
                return f'<div class="v" style="{style}">{draw_lines(w, h, cats, [(name, data[name], series_colour(objs, name, 0))])}</div>'
            if t == "lineClusteredColumnComboChart":
                y2 = R["Y2"][0][0][2]
                fam2, df2 = frame_for(R["Y2"][0][0][1])
                g2 = dict((k.strftime("%-d %b %y") if ccol == "run_date" else k, self.E.measure(fam2, y2, g))
                          for k, g in self.E.groups(fam2, df2, cent, ccol))
                line = (y2, [g2.get(c) for c in cats], series_colour(objs, y2, 1))
            series = [(s, vals, series_colour(objs, s, i)) for i, (s, vals) in enumerate(data.items())]
            if len(series) == 1 and not series_role:
                pc = [series_colour(objs, c, 0) for c in cats]
                if len(set(pc)) > 1:
                    series = [(series[0][0], series[0][1], pc)]
            horizontal = t in ("barChart", "clusteredBarChart")
            return f'<div class="v" style="{style}">{draw_column(w, h, cats, series, objs, stacked=t != "clusteredBarChart", horizontal=horizontal, line=line)}</div>'

        if t == "pivotTable":
            (_, rent, rcol), _ = R["Rows"][0]
            (_, cent, ccol), _ = R["Columns"][0]
            (_, ment, mname), _ = R["Values"][0]
            fam, df = frame_for(ment)
            rows = self.E.groups(fam, df, rent, rcol)
            colvals = sorted({k for k, _ in self.E.groups(fam, df, cent, ccol)})
            if rent == "dim_department":
                order = ["Accounts & Trust", "Compliance & AML", "HR & Payroll", "Property", "Privacy & IT"]
                rows.sort(key=lambda r: order.index(r[0]) if r[0] in order else 9)
            elif rent == "capacity_monthly":
                rows.sort(key=lambda r: r[0])
            colour_m = None
            for o in objs.get("values", []):
                bc = o.get("properties", {}).get("backColor", {})
                m = bc.get("solid", {}).get("color", {}).get("expr", {}).get("Measure")
                if m:
                    colour_m = m["Property"]
            heads = [rcol.replace("_", " ").title() if rcol != "department" else "Department"] + \
                    [c.strftime("%b %Y") if isinstance(c, pd.Timestamp) else c for c in colvals] + \
                    ([] if fam == "capacity_monthly" else ["Total"])
            body, cols = [], []
            for rv, rdf in rows:
                cells, cc = [rv], [None]
                gmap = dict(self.E.groups(fam, rdf, cent, ccol))
                for c in colvals:
                    sub = gmap.get(c)
                    val = self.E.measure(fam, mname, sub) if sub is not None and len(sub) else None
                    cells.append(fmt(val, mname))
                    cc.append(("background", self.E.measure(fam, colour_m, sub)) if colour_m and sub is not None and len(sub) else None)
                if fam != "capacity_monthly":
                    cells.append(fmt(self.E.measure(fam, mname, rdf), mname))
                    cc.append(None)
                body.append(cells)
                cols.append(cc)
            if fam != "capacity_monthly":
                tot = ["Total"] + [fmt(self.E.measure(fam, mname, g), mname) if len(g) else "" for _, g in
                                   sorted(self.E.groups(fam, df, cent, ccol), key=lambda p: colvals.index(p[0]))] + [fmt(self.E.measure(fam, mname, df), mname)]
                body.append(tot)
                cols.append([("font-weight", "700")] * len(tot))
            fs = prop(objs, "values", "fontSize", 12)
            return f'<div class="v" style="{style}">{draw_table(w, h, heads, body, cols, [150 if fam == "capacity_monthly" else 170] + [None] * (len(heads) - 1), int(fs), zebra=False)}</div>'

        if t == "tableEx":
            fields = R["Values"]
            ent = fields[0][0][1]
            fam, df = frame_for(ent)
            df = df.copy()
            sd = self.sort_def(vi)
            if sd:
                (k, e, n), d = sd[0]
                df = df.sort_values(n, ascending=d != "Descending", na_position="last")
            else:
                df = df.sort_values(fields[0][0][2], na_position="last")
            heads = [dn or n for (k, e, n), dn in fields]
            widths = {}
            for o in objs.get("columnWidth", []):
                widths[o["selector"]["metadata"].split(".")[-1]] = lit(o["properties"]["value"])
            wl = [widths.get(n) for (k, e, n), dn in fields]
            colour_rule = None
            for o in objs.get("values", []):
                fc = o.get("properties", {}).get("fontColor", {}).get("solid", {}).get("color", {}).get("expr", {}).get("Measure")
                if fc:
                    colour_rule = (o["selector"]["metadata"].split(".")[-1], fc["Property"])
            rows, cols = [], []
            for _, r in df.head(200).iterrows():
                cells, cc = [], []
                for (k, e, n), dn in fields:
                    v = r[n]
                    cells.append(fmt(v, n) if not pd.isna(v) else "")
                    if colour_rule and colour_rule[0] == n:
                        cc.append(("color", self.E.measure(fam, colour_rule[1], df.loc[[r.name]])))
                    else:
                        cc.append(None)
                rows.append(cells)
                cols.append(cc)
            fs = prop(objs, "values", "fontSize", 12)
            if not rows:
                rows = [["(no rows: the weekly run log is empty in sample mode)"] + [""] * (len(heads) - 1)] if ent == "run_log" else []
                cols = [None]
            return f'<div class="v" style="{style}">{draw_table(w, h, heads, rows, cols, wl, int(fs))}</div>'
        return f'<div class="v unk" style="{style}">{esc(t)}</div>'

    def page(self, pid):
        pj = json.loads((PAGES / pid / "page.json").read_text())
        bg = json.dumps(pj.get("objects", {}))
        img = None
        if "ItemName" in bg:
            img = bg.split('"ItemName": "')[1].split('"')[0]
        filters = pj.get("filterConfig", {}).get("filters", [])
        filters = [f for f in filters if f.get("filter")]
        vs = []
        for vf in sorted((PAGES / pid / "visuals").glob("*/visual.json")):
            v = json.loads(vf.read_text())
            if "visual" not in v or v.get("isHidden"):
                continue
            vs.append(self.visual(v, filters))
        return pj, img, "".join(vs)

    def build(self, out: Path):
        order = json.loads((PAGES / "pages.json").read_text())["pageOrder"]
        imgs, layers, names = {}, [], []
        for pid in order:
            pj, img, body = self.page(pid)
            if pj.get("visibility") == "HiddenInViewMode":
                continue
            if img and img not in imgs:
                imgs[img] = base64.b64encode((RES / img).read_bytes()).decode()
            names.append((pid, pj["displayName"]))
            layers.append(f'<section class="page" id="{pid}" data-bg="{img or ""}" style="width:{pj["width"]}px;height:{pj["height"]}px">{body}</section>')
        css_bg = "".join(f'.page[data-bg="{k}"]{{background-image:url(data:image/png;base64,{v})}}' for k, v in imgs.items())
        tabs = "".join(f'<a href="#{p}" data-go="{p}">{esc(n)}</a>' for p, n in names)
        as_of = self.D.as_of.strftime("%-d %b %Y")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEMPLATE.replace("/*BG*/", css_bg).replace("<!--PAGES-->", "".join(layers)).replace("<!--TABS-->", tabs)
                       .replace("{{FIRST}}", names[0][0]).replace("{{ASOF}}", as_of), encoding="utf-8")
        return out


TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Regulatory Change Monitor · Power BI report · Brian Phu</title>
<meta name="description" content="Power BI report for a law firm's regulatory change monitor: volume, impact, cost and team capacity. Rendered from the report's own page files. By Brian Phu.">
<meta property="og:title" content="Regulatory Change Monitor · Power BI report">
<meta property="og:description" content="Which regulatory changes matter to a law firm, what they cost, and whether the team has the hours.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ccircle cx='8' cy='8' r='8' fill='%231f2933'/%3E%3Ctext x='8' y='11' font-size='8' font-family='Arial' font-weight='700' text-anchor='middle' fill='%23b6d94c'%3EBP%3C/text%3E%3C/svg%3E">
<style>
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#e9eef4;font-family:'Segoe UI',system-ui,-apple-system,Arial,sans-serif;color:#1f2933}
.app{display:grid;grid-template-rows:32px 1fr 30px;height:100vh}
.top{background:#252423;color:#fff;display:flex;align-items:center;gap:12px;padding:0 14px;font-size:13px}
.logo{width:20px;height:20px;display:grid;grid-template-columns:repeat(3,1fr);gap:2px;align-items:end}.logo i{background:#f2c811;display:block;border-radius:1px}
.top .note{margin-left:auto;color:#c8c6c4;font-size:12px}.top a{color:#fff;text-decoration:none;border:1px solid #605e5c;border-radius:4px;padding:3px 9px;font-size:12px;white-space:nowrap}
.top a:hover{background:#3b3a39}@media (max-width:900px){.top .note,.top .sub{display:none}.top a{margin-left:auto}}
.stage{position:relative;overflow:hidden}
.canvas{position:absolute;width:1920px;height:1080px;transform-origin:0 0}
.page{position:absolute;left:0;top:0;display:none;background-size:100% 100%;background-color:#e6eaee;box-shadow:0 2px 12px rgba(0,0,0,.18)}
.page.on{display:block}
/*BG*/
.v{position:absolute;overflow:hidden}
.nav{display:block;cursor:pointer}.nav:hover{background:rgba(182,217,76,.12);border-radius:6px}
.card{display:flex;align-items:flex-end;justify-content:center;padding-bottom:8px;font-weight:600;font-family:'Segoe UI Semibold','Segoe UI',sans-serif}
.card.txt{align-items:center;padding:0 22px;font-weight:600;font-size:17px!important;line-height:1.35;text-align:center}
.slicer .st{font-size:12px;font-weight:600;color:#b6d94c;padding:2px 4px}.slicer .sb{margin:2px 4px;background:#EEF5D3;border-radius:2px;padding:6px 8px;font-size:12px;display:flex;justify-content:space-between}
.textbox p{margin:0 0 2px;line-height:1.3}
.tbl{overflow:auto;background:transparent}.tbl table{border-collapse:collapse;width:100%;table-layout:fixed}
.tbl th{position:sticky;top:0;background:#1f2933;color:#b6d94c;text-align:left;padding:6px 8px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tbl td{padding:5px 8px;border-bottom:1px solid #dfe5ea;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:top}
.tbl tr:last-child td{border-bottom:0}
.tabs{background:#f3f2f1;border-top:1px solid #e1dfdd;display:flex;align-items:center;gap:2px;padding:0 8px;overflow-x:auto;font-size:12px;white-space:nowrap}
.tabs a{color:#323130;text-decoration:none;padding:6px 12px;border-bottom:3px solid transparent}.tabs a.on{font-weight:600;border-bottom-color:#b6d94c;background:#fff}
.rot{display:none;position:absolute;top:10px;left:0;right:0;text-align:center;font-size:13px;color:#475569}
@media (max-width:700px) and (orientation:portrait){.rot{display:block}}
</style></head><body>
<div class="app">
 <div class="top"><div class="logo"><i style="height:8px"></i><i style="height:13px"></i><i style="height:18px"></i></div>
  <b>RegulatoryChangeMonitor</b><span class="sub" style="color:#c8c6c4">· Power BI report</span>
  <span class="note">Rendered from the report's own page files · sample data as at {{ASOF}} · static view (no cross-filtering)</span>
  <a href="https://github.com/brianphu2310/Regulartory_Change_Monitor" target="_blank" rel="noopener">Source on GitHub &#8599;</a></div>
 <div class="stage" id="stage"><div class="rot">&#8635; Turn your phone sideways for a bigger view</div><div class="canvas" id="canvas"><!--PAGES--></div></div>
 <div class="tabs" id="tabs"><!--TABS--></div>
</div>
<script>
const stage=document.getElementById('stage'),canvas=document.getElementById('canvas');
function fit(){const W=stage.clientWidth,H=stage.clientHeight,s=Math.min((W-12)/1920,(H-12)/1080);canvas.style.transform=`scale(${s})`;
 canvas.style.left=(W-1920*s)/2+'px';canvas.style.top=(H-1080*s)/2+'px'}
function go(id){if(!document.getElementById(id))id='{{FIRST}}';document.querySelectorAll('.page').forEach(p=>p.classList.toggle('on',p.id===id));
 document.querySelectorAll('.tabs a').forEach(a=>a.classList.toggle('on',a.dataset.go===id))}
addEventListener('hashchange',()=>go(location.hash.slice(1)));addEventListener('resize',fit);fit();go(location.hash.slice(1)||'{{FIRST}}');
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="bi_export")
    ap.add_argument("--out", default=str(ROOT / "preview" / "report.html"))
    a = ap.parse_args()
    out = Renderer(a.dataset).build(Path(a.out))
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
