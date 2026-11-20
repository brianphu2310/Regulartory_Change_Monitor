"""Impact model: what each regulatory change costs the firm in money, time and people.

Reads the star-schema CSVs in bi_export/ and writes five more tables for Power BI:

  impact_assumptions.csv  the editable rule book: effort, external cost and role split per topic
  dim_role.csv            roles, loaded hourly cost and hours a month each role can give to regulatory work
  change_effort.csv       one row per change x role: one-off hours and cost, ongoing hours and cost a year
  change_impact.csv       one row per change: total cost, hours, target date, lead time, work status
  capacity_monthly.csv    one row per month x role: hours the outstanding work needs vs hours available

Every number comes from the rules below, not from a model, so a reviewer can trace any figure back to an assumption.
All amounts are ASSUMPTIONS for a fictional small NSW law firm (AUD, ex GST); they are not quotes or benchmarks.

    python impact_model.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent / "bi_export"

# role: department, loaded hourly cost (salary + super + overheads), internal?, hours a month available for regulatory work
ROLES = {
    "Principal":             ("Management",       250, True,  10),
    "Solicitor":             ("Legal",            120, True,  16),
    "Conveyancer":           ("Property",          75, True,  12),
    "Compliance Officer":    ("Compliance & AML",  80, True,  40),
    "Trust Account Manager": ("Accounts & Trust",  65, True,  14),
    "Accounts Officer":      ("Accounts & Trust",  55, True,  12),
    "HR & Payroll Officer":  ("HR & Payroll",      55, True,  12),
    "Practice Manager":      ("Management",        70, True,  14),
    "IT Consultant":         ("Privacy & IT",     150, False, 10),
}

# topic: one-off hours for a Medium-impact change that needs action, ongoing hours a year (High impact only),
#        external one-off cost, external ongoing cost a year, split of the hours across roles
TOPICS = {
    "AML/CTF":        (12, 8, 400, 300, {"Compliance Officer": .50, "Principal": .15, "Solicitor": .15, "Practice Manager": .10, "IT Consultant": .10}),
    "Sanctions":      (4, 2, 0, 0,       {"Compliance Officer": .70, "Solicitor": .30}),
    "Trust Accounts": (6, 4, 150, 0,    {"Trust Account Manager": .60, "Principal": .20, "Accounts Officer": .20}),
    "Tax":            (4, 2, 100, 0,      {"Accounts Officer": .80, "Principal": .20}),
    "Payroll":        (3, 1, 100, 0,      {"HR & Payroll Officer": .70, "Accounts Officer": .30}),
    "Superannuation": (2, 0, 0, 0,        {"HR & Payroll Officer": .80, "Accounts Officer": .20}),
    "Employment":     (5, 2, 300, 0,     {"HR & Payroll Officer": .50, "Practice Manager": .30, "Principal": .20}),
    "Property":       (3, 1, 50, 0,      {"Conveyancer": .70, "Solicitor": .30}),
    "Privacy & Data": (8, 4, 600, 200, {"IT Consultant": .40, "Practice Manager": .30, "Principal": .15, "Compliance Officer": .15}),
}
IMPACT_FACTOR = {"High": 2.0, "Medium": 1.0, "Low": 0.3}
AWARENESS_HOURS = 0.5          # a change with no action still has to be read and filed by its owner
TARGET_DAYS = {"High": 30, "Medium": 60, "Low": 90}   # target date when the change has no stated deadline


def _owner(split: dict) -> str:
    return max(split, key=split.get)


def build(out: Path = OUT, as_of: pd.Timestamp | None = None) -> dict[str, pd.DataFrame]:
    """Write the five impact tables next to changes.csv in `out`. `as_of` defaults to the latest published date."""
    changes = pd.read_csv(out / "changes.csv", parse_dates=["published", "deadline"])
    topics = pd.read_csv(out / "change_topics.csv")
    as_of = pd.Timestamp(as_of) if as_of is not None else changes["published"].max()

    assumptions = pd.DataFrame([
        {"topic": t, "one_off_hours_medium": h, "ongoing_hours_yr": oh, "external_one_off": e1,
         "external_ongoing_yr": e2, "role": r, "share": s}
        for t, (h, oh, e1, e2, split) in TOPICS.items() for r, s in split.items()])
    roles = pd.DataFrame([{"role": r, "department": d, "hourly_cost": c, "internal": i, "reg_hours_per_month": h}
                          for r, (d, c, i, h) in ROLES.items()])
    rate = roles.set_index("role")["hourly_cost"]

    eff, ext = [], {}
    for _, ch in changes.iterrows():
        ts = [t for t in topics.loc[topics["id"] == ch["id"], "topic"] if t in TOPICS]
        if not ts:   # no known topic: someone still reads and files it
            eff.append((ch["id"], "Practice Manager", AWARENESS_HOURS, 0.0))
            ext[ch["id"]] = (0.0, 0.0)
            continue
        f = IMPACT_FACTOR[ch["impact"]]
        e1 = e2 = 0.0
        for t in ts:
            h, oh, x1, x2, split = TOPICS[t]
            if ch["action_req"] == 1:
                for r, s in split.items():
                    ongoing = oh * s / len(ts) if ch["impact"] == "High" else 0.0
                    eff.append((ch["id"], r, h * f * s / len(ts), ongoing))
                e1 += x1 * f / len(ts)
                e2 += x2 / len(ts) if ch["impact"] == "High" else 0.0
            else:
                eff.append((ch["id"], _owner(split), AWARENESS_HOURS / len(ts), 0.0))
        ext[ch["id"]] = (round(e1, 2), round(e2, 2))

    effort = (pd.DataFrame(eff, columns=["id", "role", "one_off_hours", "ongoing_hours_yr"])
              .groupby(["id", "role"], as_index=False).sum())
    effort["one_off_cost"] = (effort["one_off_hours"] * effort["role"].map(rate)).round(2)
    effort["ongoing_cost_yr"] = (effort["ongoing_hours_yr"] * effort["role"].map(rate)).round(2)
    effort[["one_off_hours", "ongoing_hours_yr"]] = effort[["one_off_hours", "ongoing_hours_yr"]].round(2)

    tot = effort.groupby("id")[["one_off_hours", "ongoing_hours_yr", "one_off_cost", "ongoing_cost_yr"]].sum()
    imp = changes[["id", "published", "deadline", "impact", "action_req", "status"]].set_index("id").join(tot)
    imp["external_one_off"] = [ext[i][0] for i in imp.index]
    imp["external_ongoing_yr"] = [ext[i][1] for i in imp.index]
    imp["internal_one_off_cost"] = imp.pop("one_off_cost")
    imp["internal_ongoing_cost_yr"] = imp.pop("ongoing_cost_yr")
    imp["total_one_off_cost"] = imp["internal_one_off_cost"] + imp["external_one_off"]
    imp["total_ongoing_cost_yr"] = imp["internal_ongoing_cost_yr"] + imp["external_ongoing_yr"]
    imp["target_date"] = imp["deadline"].fillna(imp["published"] + pd.to_timedelta(imp["impact"].map(TARGET_DAYS), "D"))
    imp["lead_time_days"] = (imp["target_date"] - imp["published"]).dt.days
    imp["days_left"] = (imp["target_date"] - as_of).dt.days
    imp["work_status"] = "Awareness only"
    imp.loc[imp["action_req"] == 1, "work_status"] = "Outstanding"
    imp.loc[(imp["action_req"] == 1) & (imp["status"] == "Actioned"), "work_status"] = "Done"
    imp["outstanding_hours"] = imp["one_off_hours"].where(imp["work_status"] == "Outstanding", 0.0)
    imp["at_risk"] = ((imp["work_status"] == "Outstanding") & (imp["days_left"] < 14)).astype(int)
    imp["as_of"] = as_of
    for c in ("published", "deadline", "target_date", "as_of"):
        imp[c] = imp[c].dt.date
    imp = imp.drop(columns=["impact", "action_req", "status"]).round(2).reset_index()

    # capacity: spread each outstanding change's hours evenly over the months from as_of to its target date
    # (overdue work lands in the as_of month, because it has to be done now)
    rows = []
    out_ids = set(imp.loc[imp["work_status"] == "Outstanding", "id"])
    tgt = imp.set_index("id")["target_date"]
    for _, e in effort[effort["id"].isin(out_ids)].iterrows():
        months = pd.period_range(as_of.to_period("M"), max(pd.Timestamp(tgt[e["id"]]), as_of).to_period("M"), freq="M")
        for m in months:
            rows.append((m.to_timestamp().date(), e["role"], e["one_off_hours"] / len(months)))
    need = pd.DataFrame(rows, columns=["month_start", "role", "hours_required"]).groupby(["month_start", "role"], as_index=False).sum()
    grid = pd.MultiIndex.from_product([sorted(need["month_start"].unique()), roles["role"]], names=["month_start", "role"]).to_frame(index=False)
    cap = grid.merge(need, how="left").fillna({"hours_required": 0.0})
    cap["hours_available"] = cap["role"].map(roles.set_index("role")["reg_hours_per_month"]).astype(float)
    cap["load_pct"] = (cap["hours_required"] / cap["hours_available"]).round(3)
    cap["hours_over_capacity"] = (cap["hours_required"] - cap["hours_available"]).clip(lower=0).round(2)
    cap["hours_required"] = cap["hours_required"].round(2)

    # one wide table for the focused dashboard: the change, its cost and time, and who leads it
    lead = effort.sort_values("one_off_hours", ascending=False).drop_duplicates("id").set_index("id")["role"]
    dash = changes[["id", "published", "source", "title", "link", "impact", "impact_sort", "topics", "status", "action_req"]].drop(columns="published").merge(imp, on="id")
    dash["lead_role"] = dash["id"].map(lead)
    dash["lead_department"] = dash["lead_role"].map(roles.set_index("role")["department"])
    dash["published"] = pd.to_datetime(dash["published"]).dt.date
    effort = effort.merge(roles[["role", "department", "hourly_cost"]], on="role")

    tables = {"impact_assumptions": assumptions, "dim_role": roles, "change_effort": effort,
              "change_impact": imp, "capacity_monthly": cap, "dashboard_changes": dash}
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False)
    return tables


if __name__ == "__main__":
    t = build()
    imp, cap = t["change_impact"], t["capacity_monthly"]
    print(f"One-off cost of all changes needing action: ${imp['total_one_off_cost'].sum():,.0f}")
    print(f"Ongoing cost a year: ${imp['total_ongoing_cost_yr'].sum():,.0f}")
    print(f"Outstanding hours: {imp['outstanding_hours'].sum():,.0f} across {(imp['work_status'] == 'Outstanding').sum()} changes")
    over = cap[cap["hours_over_capacity"] > 0]
    print(f"Role-months over capacity: {len(over)}")
    print(over.sort_values("hours_over_capacity", ascending=False).head(5).to_string(index=False))
