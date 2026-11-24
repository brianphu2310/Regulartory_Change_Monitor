"""Refresh the data block of the HTML preview (Finance impact and Capacity pages) from the impact-model exports.

    python preview/build_preview.py

Reads bi_export/ (synthetic year) and data/live/run_log.csv (latest real weekly run) and rewrites the
`const FIN=` line between the FIN markers in preview/dashboard_preview.html. No network needed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "preview" / "dashboard_preview.html"
START, END = "/*FIN:start*/", "/*FIN:end*/"


def payload() -> dict:
    d = pd.read_csv(ROOT / "bi_export" / "dashboard_changes.csv").fillna({"lead_role": "", "lead_department": "Other", "title": ""})
    ids = {k: i for i, k in enumerate(d["id"])}
    rows = [[r.source, r.impact, r.work_status, int(r.days_left), r.first_seen, round(r.total_one_off_cost, 2),
             round(r.internal_one_off_cost, 2), round(r.external_one_off, 2), round(r.total_ongoing_cost_yr, 2),
             round(r.outstanding_hours, 2), r.lead_department, r.target_date, r.title, r.lead_role] for r in d.itertuples()]
    e = pd.read_csv(ROOT / "bi_export" / "change_effort.csv")
    effort = [[ids[r.id], r.role, round(r.one_off_hours, 2)] for r in e.itertuples() if r.id in ids]
    roles = pd.read_csv(ROOT / "bi_export" / "dim_role.csv")
    cap = pd.read_csv(ROOT / "bi_export" / "capacity_monthly.csv")
    log = pd.read_csv(ROOT / "data" / "live" / "run_log.csv")
    log_date = log["run_at"].str[:10].max()
    last = log[log["run_at"].str[:10] == log_date].sort_values("run_at").groupby("agency", sort=False).tail(1)
    return {
        "asOf": str(d["as_of"].max()),
        "agencies": sorted(d["source"].unique().tolist()),
        "rows": rows,
        "effort": effort,
        "roles": [[r.role, int(r.reg_hours_per_month)] for r in roles.itertuples() if r.role in set(cap["role"])],
        "cap": [[r.month_start, r.role, round(r.hours_required, 2), round(r.hours_available, 2), round(r.hours_over_capacity, 2)]
                for r in cap.itertuples()],
        "logDate": log_date,
        "log": [[r.agency, str(r.status), int(r.items)] for r in last.itertuples()],
    }


def main() -> None:
    s = HTML.read_text(encoding="utf-8")
    a, b = s.index(START) + len(START), s.index(END)
    s = s[:a] + "const FIN=" + json.dumps(payload(), separators=(",", ":")) + ";" + s[b:]
    HTML.write_text(s, encoding="utf-8")
    print(f"updated {HTML.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
