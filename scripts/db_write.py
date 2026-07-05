from pathlib import Path
import sqlite3

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "current.db"


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# ── Migration ────────────────────────────────────────────────────────────────

def migrate(conn: sqlite3.Connection) -> None:
    """
    Idempotent: adds columns introduced after the initial schema deploy.
    Called by db_init.py on every run so existing databases stay current.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    if "category" not in existing:
        conn.execute("ALTER TABLE items ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        conn.commit()


# ── Read ─────────────────────────────────────────────────────────────────────

def item_exists(source_id: str) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT 1 FROM items WHERE source_id = ? LIMIT 1",
            (source_id,),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


# ── Write ────────────────────────────────────────────────────────────────────

def insert_item(
    item_id:    str,
    source_id:  str,
    title:      str,
    content:    str,
    created_at: str,
    run_id:     str,
    category:   str = "",
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO items
               (id, source_id, title, content, created_at, run_id, category)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (item_id, source_id, title, content, created_at, run_id, category),
        )
        conn.commit()
    finally:
        conn.close()


def insert_error(
    run_id:     str,
    source_id:  str,
    stage:      str,
    error_type: str,
    message:    str,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO errors (run_id, source_id, stage, error_type, message)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, source_id, stage, error_type, message),
        )
        conn.commit()
    finally:
        conn.close()
