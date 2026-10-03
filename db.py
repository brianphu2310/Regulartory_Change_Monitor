"""SQLite storage for regulatory changes."""
import hashlib
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent / "data" / "changes.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS changes (
    id           TEXT PRIMARY KEY,
    published    TEXT NOT NULL,          -- ISO date YYYY-MM-DD
    source       TEXT NOT NULL,          -- AUSTRAC / ATO / Fair Work / ...
    title        TEXT NOT NULL,
    summary      TEXT,
    link         TEXT,
    topics       TEXT,                   -- comma separated
    impact       TEXT,                   -- High / Medium / Low
    audiences    TEXT,                   -- comma separated
    action_req   INTEGER DEFAULT 0,      -- 1 = needs action
    deadline     TEXT,                   -- ISO date or NULL
    is_sample    INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'New'      -- New / Reviewed / Actioned
);
CREATE INDEX IF NOT EXISTS idx_changes_pub ON changes(published);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def make_id(source: str, title: str, link: str | None) -> str:
    """Stable id so re-collecting the same item never creates a duplicate."""
    raw = f"{source}|{(link or title).strip().lower()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def upsert(conn: sqlite3.Connection, item: dict) -> bool:
    """Insert an item. Returns True if new, False if it already existed.
    Existing rows keep their user-set status."""
    cur = conn.execute("SELECT 1 FROM changes WHERE id = ?", (item["id"],))
    if cur.fetchone():
        return False
    conn.execute(
        """INSERT INTO changes
           (id, published, source, title, summary, link, topics, impact,
            audiences, action_req, deadline, is_sample, status)
           VALUES (:id, :published, :source, :title, :summary, :link, :topics,
                   :impact, :audiences, :action_req, :deadline, :is_sample, 'New')""",
        item,
    )
    conn.commit()
    return True


def load_df(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM changes ORDER BY published DESC", conn)
    if not df.empty:
        df["published"] = pd.to_datetime(df["published"])
        df["deadline"] = pd.to_datetime(df["deadline"], errors="coerce")
    return df


def set_status(conn: sqlite3.Connection, item_id: str, status: str) -> None:
    conn.execute("UPDATE changes SET status = ? WHERE id = ?", (status, item_id))
    conn.commit()


def clear_sample(conn: sqlite3.Connection) -> int:
    n = conn.execute("DELETE FROM changes WHERE is_sample = 1").rowcount
    conn.commit()
    return n
