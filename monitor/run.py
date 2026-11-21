"""One monitoring run: fetch every source, keep what is new and relevant, classify it, cost it, write a report.

    python -m monitor.run            # writes data/live/ and reports/latest.md
    python -m monitor.run --dry-run  # fetch and print, write nothing

Exit code is 0 even when a source fails: failures are recorded in data/live/run_log.csv and in the report.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import impact_model
from classifier import classify

from .fetch import fetch, item_id
from .sources import SOURCES

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "data" / "live"
REPORT = ROOT / "reports" / "latest.md"
MAX_AGE_DAYS = 365
IMPACT_SORT = {"High": 1, "Medium": 2, "Low": 3}
CHANGE_COLS = ["id", "published", "first_seen", "source", "feed", "title", "summary", "link", "impact", "action_req",
               "deadline", "status", "impact_sort", "data_type", "topics", "audiences"]


def today_sydney() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=11)).date()


def _read(name: str, cols: list[str]) -> pd.DataFrame:
    p = LIVE / name
    return pd.read_csv(p, dtype=str) if p.exists() and p.stat().st_size else pd.DataFrame(columns=cols)


def collect(today: date) -> tuple[list[dict], list[dict]]:
    items, log = [], []
    for src in SOURCES:
        got, status = fetch(src)
        log.append({"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "agency": src.agency,
                    "feed": src.name, "status": status, "items": len(got)})
        items += got
    for it in items:
        it["id"] = item_id(it["link"])
        it["published"] = it["published"] or today
    cutoff = today - timedelta(days=MAX_AGE_DAYS)
    return [i for i in items if i["published"] >= cutoff and i["link"]], log


def classify_new(items: list[dict], seen: set[str], today: date) -> pd.DataFrame:
    rows, done = [], set()
    for it in items:
        if it["id"] in seen or it["id"] in done:
            continue
        done.add(it["id"])
        c = classify(it["title"], it["summary"], it["published"])
        rows.append({**{k: it[k] for k in ("id", "published", "source", "feed", "title", "summary", "link")},
                     "first_seen": today, **c, "status": "New", "impact_sort": IMPACT_SORT[c["impact"]],
                     "data_type": "Live"})
    return pd.DataFrame(rows, columns=CHANGE_COLS)


def _split(df: pd.DataFrame, col: str, name: str) -> pd.DataFrame:
    r = df[["id", col]].assign(**{col: df[col].fillna("").str.split(", ")}).explode(col)
    return r[(r[col] != "") & (r[col] != "Other") & (r[col] != "General")].rename(columns={col: name}).drop_duplicates()


def dim_date(changes: pd.DataFrame) -> pd.DataFrame:
    """Calendar for the v1 report: first published date to 180 days after the latest date seen."""
    pub = pd.to_datetime(changes["published"], errors="coerce")
    dl = pd.to_datetime(changes["deadline"], errors="coerce")
    end = max(pub.max(), dl.max() if dl.notna().any() else pub.max()) + timedelta(days=180)
    d = pd.DataFrame({"date": pd.date_range(pub.min().normalize(), end, freq="D")})
    d["year"] = d["date"].dt.year
    d["month_num"] = d["date"].dt.month
    d["month_name"] = d["date"].dt.strftime("%b")
    d["year_month"] = d["date"].dt.strftime("%Y-%m")
    d["month_start"] = d["date"].dt.to_period("M").dt.to_timestamp().dt.date
    d["week_start"] = (d["date"] - pd.to_timedelta(d["date"].dt.weekday, unit="D")).dt.date
    d["date"] = d["date"].dt.date
    return d


def report(new: pd.DataFrame, impact: pd.DataFrame | None, log: list[dict], today: date, baseline: bool) -> str:
    ok = sum(1 for l in log if l["status"].startswith("ok"))
    lines = [f"# Regulatory change report: {today:%d %b %Y}", "",
             f"Sources checked: {len(log)} ({ok} ok). " + ("**Baseline run:** existing items loaded, nothing flagged as new."
                                                           if baseline else f"New relevant changes: **{len(new)}**."), ""]
    if not baseline and len(new):
        imp = impact.set_index("id") if impact is not None else None
        lines += ["| Agency | Change | Impact | Action | Deadline | Est. cost | Hours | Topics |",
                  "|---|---|---|---|---|---|---|---|"]
        for _, r in new.sort_values(["impact_sort", "published"]).iterrows():
            cost = f"${imp.at[r['id'], 'total_one_off_cost']:,.0f}" if imp is not None and r["id"] in imp.index else "-"
            hrs = f"{imp.at[r['id'], 'one_off_hours']:.1f}" if imp is not None and r["id"] in imp.index else "-"
            lines.append(f"| {r['source']} | [{r['title'][:90]}]({r['link']}) | {r['impact']} | "
                         f"{'Yes' if int(r['action_req']) else 'No'} | {r['deadline'] or '-'} | {cost} | {hrs} | {r['topics']} |")
        if impact is not None:
            sel = impact[impact["id"].isin(new["id"])]
            lines += ["", f"**Estimated effect of this run's changes:** ${sel['total_one_off_cost'].sum():,.0f} one-off, "
                          f"${sel['total_ongoing_cost_yr'].sum():,.0f} a year ongoing, {sel['one_off_hours'].sum():.0f} staff hours."]
    lines += ["", "## Source health", "", "| Agency | Feed | Status |", "|---|---|---|"]
    lines += [f"| {l['agency']} | {l['feed']} | {l['status']} |" for l in log]
    lines += ["", "_Tags come from keyword rules (`classifier.py`); costs and hours are estimates from the assumptions "
                  "in `impact_model.py`. Not legal advice._"]
    return "\n".join(lines) + "\n"


def main(dry: bool = False) -> int:
    today = today_sydney()
    items, log = collect(today)
    old = _read("changes.csv", CHANGE_COLS)
    seen_df = _read("seen.csv", ["id", "first_seen"])
    baseline = seen_df.empty
    seen = set(seen_df["id"])
    fresh = classify_new(items, seen, today)
    relevant = fresh[fresh["topics"] != "Other"]
    print(f"{len(items)} items fetched, {len(fresh)} unseen, {len(relevant)} relevant")
    for l in log:
        print(f"  {l['agency']:<9} {l['feed']:<34} {l['status']}")
    if dry:
        return 0

    LIVE.mkdir(parents=True, exist_ok=True)
    if not old.empty:
        old["status"] = old["status"].replace("New", "Reviewed")
    changes = pd.concat([old, relevant.astype(str)], ignore_index=True)
    changes = changes.replace({"None": "", "nan": ""})
    changes.to_csv(LIVE / "changes.csv", index=False)
    _split(changes, "topics", "topic").to_csv(LIVE / "change_topics.csv", index=False)
    _split(changes, "audiences", "audience").to_csv(LIVE / "change_audiences.csv", index=False)
    if len(changes):
        dim_date(changes).to_csv(LIVE / "dim_date.csv", index=False)
    pd.DataFrame(items, columns=["source", "feed", "via", "published", "title", "link", "id"]).merge(
        fresh[["id", "topics", "impact"]], on="id", how="left").to_csv(LIVE / "fetched_latest.csv", index=False)
    pd.concat([seen_df, pd.DataFrame({"id": fresh["id"], "first_seen": str(today)})]).to_csv(LIVE / "seen.csv", index=False)
    log_path = LIVE / "run_log.csv"
    pd.DataFrame(log).to_csv(log_path, mode="a", header=not log_path.exists(), index=False)

    impact = None
    if len(changes):
        impact = impact_model.build(LIVE, as_of=pd.Timestamp(today))["change_impact"]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(report(relevant, impact, log, today, baseline), encoding="utf-8")

    flagged = 0 if baseline else len(relevant)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"new_changes={flagged}\nhigh_impact={int((relevant['impact'] == 'High').sum()) if flagged else 0}\n")
    print(f"Report written to {REPORT.name}; flagged {flagged} new changes")
    return 0


if __name__ == "__main__":
    sys.exit(main("--dry-run" in sys.argv))
