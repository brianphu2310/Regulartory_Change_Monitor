"""Export the database as clean CSV tables for Power BI / Tableau / Excel.

Usage:
  python export_for_bi.py            # export what is in data/changes.db
  python export_for_bi.py --sample   # load sample data first if the DB is empty

Writes to ./bi_export/ :
  changes.csv          one row per regulatory change (fact table)
  change_topics.csv    id, topic        (one row per topic tag)
  change_audiences.csv id, audience     (one row per affected audience)
  dim_date.csv         calendar table covering all dates + 180 days ahead
"""
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

import db

OUT = Path(__file__).parent / "bi_export"
IMPACT_SORT = {"High": 1, "Medium": 2, "Low": 3}


def _split(df: pd.DataFrame, col: str, name: str) -> pd.DataFrame:
    rows = df[["id", col]].copy()
    rows[col] = rows[col].fillna("").str.split(", ")
    rows = rows.explode(col)
    rows = rows[rows[col] != ""].rename(columns={col: name})
    return rows.drop_duplicates()


def export() -> dict:
    conn = db.connect()
    df = db.load_df(conn)
    if df.empty:
        raise SystemExit("Database is empty. Run with --sample to generate the synthetic dataset.")
    OUT.mkdir(exist_ok=True)

    fact = df.copy()
    fact["impact_sort"] = fact["impact"].map(IMPACT_SORT)
    fact["published"] = fact["published"].dt.date
    fact["deadline"] = fact["deadline"].dt.date
    fact["data_type"] = fact["is_sample"].map({1: "Sample", 0: "Real"})
    fact = fact.drop(columns=["topics", "audiences", "is_sample"]).assign(
        topics=df["topics"], audiences=df["audiences"]
    )
    fact.to_csv(OUT / "changes.csv", index=False)

    _split(df, "topics", "topic").to_csv(OUT / "change_topics.csv", index=False)
    _split(df, "audiences", "audience").to_csv(OUT / "change_audiences.csv", index=False)

    start = df["published"].min().normalize()
    end = max(df["published"].max(), df["deadline"].max() if df["deadline"].notna().any() else df["published"].max())
    end = end + timedelta(days=180)
    d = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    d["year"] = d["date"].dt.year
    d["month_num"] = d["date"].dt.month
    d["month_name"] = d["date"].dt.strftime("%b")
    d["year_month"] = d["date"].dt.strftime("%Y-%m")
    d["month_start"] = d["date"].dt.to_period("M").dt.to_timestamp().dt.date
    d["week_start"] = (d["date"] - pd.to_timedelta(d["date"].dt.weekday, unit="D")).dt.date
    d["date"] = d["date"].dt.date
    d.to_csv(OUT / "dim_date.csv", index=False)

    return {p.name: sum(1 for _ in open(p, encoding="utf-8")) - 1 for p in sorted(OUT.glob("*.csv"))}


if __name__ == "__main__":
    if "--sample" in sys.argv:
        import generate_synthetic
        c = db.connect()
        if db.load_df(c).empty:
            generate_synthetic.load(c)
    for name, rows in export().items():
        print(f"{name}: {rows} rows")
    print(f"Written to {OUT}")
