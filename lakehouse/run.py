"""Load one monitor run into the lakehouse: bronze -> quality gate -> silver -> gold.

    # on Databricks (what GitHub Actions runs after the weekly monitor)
    DATABRICKS_HOST=... DATABRICKS_TOKEN=... DATABRICKS_WAREHOUSE_ID=... python -m lakehouse.run --source data/live

    # locally, same SQL, on DuckDB (used by the tests and the sample backfill)
    python -m lakehouse.run --source data/live --local lakehouse/local/workspace.duckdb

The SQL in lakehouse/sql/ is written for Databricks SQL. Locally each statement is translated to DuckDB with sqlglot,
so the logic that runs in the cloud is the logic the tests check. After the load, gold.weekly_snapshot and the quality
results are written back next to the CSVs (weekly_snapshot.csv, quality_checks.csv) so the report also works without
Databricks.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SQL_DIR = HERE / "sql"
FILES = ["changes", "change_topics", "change_audiences", "dim_date", "dashboard_changes", "change_effort",
         "capacity_monthly", "run_log"]
SCHEMA = "rcm_bronze"


logging.getLogger("sqlglot").setLevel(logging.ERROR)   # COMMENT clauses have no DuckDB equivalent; dropping them is fine


class QualityError(RuntimeError):
    pass


def statements(text: str) -> list[tuple[str, bool]]:
    """Split a .sql file into statements. Comment lines are dropped; `-- @remote` marks the next statement Databricks-only."""
    out, buf, remote = [], [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("--"):
            remote = remote or s.startswith("-- @remote")
            continue
        if not s:
            continue
        buf.append(line)
        if s.endswith(";"):
            out.append(("\n".join(buf).rstrip().rstrip(";"), remote))
            buf, remote = [], False
    if buf:
        out.append(("\n".join(buf), remote))
    return out


class Engine:
    catalog = "workspace"

    def render(self, sql: str, run_date: str) -> str:
        sql = sql.replace("{{catalog}}", self.catalog).replace("{{run_date}}", run_date)
        return re.sub(r"\{\{src:(\w+)\}\}", lambda m: self.source(m.group(1), run_date), sql)

    def run_file(self, path: Path, run_date: str) -> None:
        for sql, remote in statements(path.read_text()):
            if remote and not self.remote:
                continue
            self.execute(self.render(sql, run_date))

    def load(self, source: Path, run_date: str) -> dict:
        self.prepare(source, run_date)
        self.run_file(SQL_DIR / "00_setup.sql", run_date)
        self.upload(source, run_date)
        self.run_file(SQL_DIR / "10_bronze.sql", run_date)
        self.run_file(SQL_DIR / "15_quality.sql", run_date)
        qc = self.query(f"SELECT check_name, blocking, failed_rows, passed FROM {self.catalog}.rcm_silver.quality_checks "
                        f"WHERE run_date = DATE '{run_date}' ORDER BY check_name")
        bad = qc[(~qc["passed"].astype(bool)) & qc["blocking"].astype(bool)]
        if len(bad):
            raise QualityError("blocking data quality checks failed:\n" + bad.to_string(index=False))
        self.run_file(SQL_DIR / "20_silver.sql", run_date)
        self.run_file(SQL_DIR / "30_gold.sql", run_date)
        snap = self.query(f"SELECT * FROM {self.catalog}.rcm_gold.weekly_snapshot ORDER BY run_date")
        checks = self.query(f"SELECT * FROM {self.catalog}.rcm_silver.quality_checks ORDER BY run_date, check_name")
        return {"quality": qc, "weekly_snapshot": snap, "quality_checks": checks}

    # hooks
    remote = False

    def prepare(self, source: Path, run_date: str) -> None:
        pass

    def upload(self, source: Path, run_date: str) -> None:
        pass


class LocalEngine(Engine):
    """DuckDB stand-in for the SQL warehouse. The database file name is the catalog name."""

    def __init__(self, db: Path):
        import duckdb
        import sqlglot
        self.sqlglot = sqlglot
        db.parent.mkdir(parents=True, exist_ok=True)
        self.catalog = db.stem
        self.con = duckdb.connect(str(db))
        self.src = None

    def prepare(self, source: Path, run_date: str) -> None:
        self.src = source

    def source(self, name: str, run_date: str) -> str:
        p = (self.src / f"{name}.csv").resolve()
        return f"read_csv('{p}', header = true, all_varchar = true)"

    def execute(self, sql: str) -> None:
        # read_csv(...) is DuckDB syntax already: keep it out of the translation
        holes = {}

        def stash(m):
            holes[f"__src{len(holes)}__"] = m.group(0)
            return f"__src{len(holes) - 1}__"
        body = re.sub(r"read_csv\('[^']+', header = true, all_varchar = true\)", stash, sql)
        out = self.sqlglot.transpile(body, read="databricks", write="duckdb")[0]
        for k, v in holes.items():
            out = out.replace(k, v)
        self.con.execute(out)

    def query(self, sql: str) -> pd.DataFrame:
        return self.con.execute(self.sqlglot.transpile(sql, read="databricks", write="duckdb")[0]).df()


class DatabricksEngine(Engine):
    """Databricks SQL warehouse through the REST APIs (Files API for the upload, Statement Execution API for SQL)."""
    remote = True

    def __init__(self, host: str, token: str, warehouse: str, catalog: str = "workspace"):
        import requests
        self.http = requests.Session()
        self.http.headers["Authorization"] = f"Bearer {token}"
        self.base = "https://" + host.removeprefix("https://").rstrip("/")
        self.warehouse, self.catalog = warehouse, catalog

    def landing(self, run_date: str) -> str:
        return f"/Volumes/{self.catalog}/{SCHEMA}/landing/{run_date}"

    def source(self, name: str, run_date: str) -> str:
        return (f"read_files('{self.landing(run_date)}/{name}.csv', format => 'csv', header => true, "
                f"inferColumnTypes => false, multiLine => true, escape => '\"')")

    def upload(self, source: Path, run_date: str) -> None:
        for name in FILES:
            p = source / f"{name}.csv"
            r = self.http.put(f"{self.base}/api/2.0/fs/files{self.landing(run_date)}/{name}.csv",
                              params={"overwrite": "true"}, data=p.read_bytes(), timeout=120)
            r.raise_for_status()
            print(f"uploaded {name}.csv")

    def _submit(self, sql: str) -> dict:
        r = self.http.post(f"{self.base}/api/2.0/sql/statements", timeout=120, json={
            "warehouse_id": self.warehouse, "statement": sql, "wait_timeout": "50s", "on_wait_timeout": "CONTINUE",
            "format": "JSON_ARRAY", "disposition": "INLINE"})
        r.raise_for_status()
        res = r.json()
        while res["status"]["state"] in ("PENDING", "RUNNING"):
            time.sleep(3)
            res = self.http.get(f"{self.base}/api/2.0/sql/statements/{res['statement_id']}", timeout=60).json()
        if res["status"]["state"] != "SUCCEEDED":
            raise RuntimeError(f"{res['status']}\n--- statement ---\n{sql[:2000]}")
        return res

    def execute(self, sql: str) -> None:
        self._submit(sql)

    def query(self, sql: str) -> pd.DataFrame:
        res = self._submit(sql)
        cols = [c["name"] for c in res["manifest"]["schema"]["columns"]]
        types = {c["name"]: c["type_name"] for c in res["manifest"]["schema"]["columns"]}
        df = pd.DataFrame(res.get("result", {}).get("data_array", []) or [], columns=cols)
        for c, t in types.items():   # the API returns every value as a string
            if t in ("INT", "BIGINT", "DOUBLE", "DECIMAL", "FLOAT", "LONG", "SHORT"):
                df[c] = pd.to_numeric(df[c])
            elif t == "BOOLEAN":
                df[c] = df[c].map({"true": True, "false": False})
        return df


def engine_from_env(local: str | None) -> Engine:
    if local:
        return LocalEngine(Path(local))
    need = ["DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"set {', '.join(missing)} (or use --local path.duckdb)")
    return DatabricksEngine(os.environ["DATABRICKS_HOST"], os.environ["DATABRICKS_TOKEN"],
                            os.environ["DATABRICKS_WAREHOUSE_ID"], os.environ.get("DATABRICKS_CATALOG", "workspace"))


def write_back(source: Path, result: dict) -> None:
    snap = result["weekly_snapshot"].copy()
    snap["run_date"] = pd.to_datetime(snap["run_date"]).dt.date
    snap.to_csv(source / "weekly_snapshot.csv", index=False)
    qc = result["quality_checks"].copy()
    qc["run_date"] = pd.to_datetime(qc["run_date"]).dt.date
    qc.drop(columns=[c for c in ("checked_at",) if c in qc]).to_csv(source / "quality_checks.csv", index=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", default="data/live", help="folder with the monitor's CSV files")
    ap.add_argument("--run-date", default=None, help="run date (default: as_of in dashboard_changes.csv)")
    ap.add_argument("--local", default=None, help="DuckDB file to use instead of Databricks")
    ap.add_argument("--no-write-back", action="store_true")
    a = ap.parse_args(argv)
    source = (ROOT / a.source) if not Path(a.source).is_absolute() else Path(a.source)
    run_date = a.run_date or str(pd.read_csv(source / "dashboard_changes.csv")["as_of"].max())[:10] or str(date.today())
    eng = engine_from_env(a.local)
    try:
        result = eng.load(source, run_date)
    except QualityError as e:
        print(e, file=sys.stderr)
        return 2
    print(result["quality"].to_string(index=False))
    print(result["weekly_snapshot"].tail(3).to_string(index=False))
    if not a.no_write_back:
        write_back(source, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
