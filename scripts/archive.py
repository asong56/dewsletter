"""
archive.py  —  Cumulative archive + feed health monitoring

archive.db  lives in the repo root and is never reset.
It grows ~N KB/week (proportional to article count + content size).

Feed health thresholds:
  GREEN  last article < 14 days ago
  AMBER  14 – 30 days ago
  RED    > 30 days ago
  GREY   never produced an article (possible dead/broken feed)
"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET

ROOT        = Path(__file__).resolve().parent.parent
CURRENT_DB  = ROOT / "current.db"
ARCHIVE_DB  = ROOT / "archive.db"
SCHEMA_PATH = ROOT / "schema.sql"
OPML_PATH   = ROOT / "feed.opml"


# ── Schema ────────────────────────────────────────────────────────────────────

def _init_archive(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text("utf-8")
    conn.executescript(schema)
    # Migration: ensure category column exists (same logic as db_write.migrate)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    if "category" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN category TEXT NOT NULL DEFAULT ''")
    conn.commit()


# ── Merge ─────────────────────────────────────────────────────────────────────

def merge() -> int:
    """
    Copy all rows from current.db into archive.db (INSERT OR IGNORE).
    Returns the number of newly inserted rows.
    """
    src = sqlite3.connect(CURRENT_DB)
    dst = sqlite3.connect(ARCHIVE_DB)

    _init_archive(dst)

    rows = src.execute("SELECT * FROM items").fetchall()
    src.close()

    col_count = len(rows[0]) if rows else 0

    if col_count == 7:
        # id, source_id, title, content, created_at, run_id, category
        dst.executemany(
            "INSERT OR IGNORE INTO items VALUES (?,?,?,?,?,?,?)", rows
        )
    elif col_count == 6:
        # legacy rows without category
        dst.executemany(
            "INSERT OR IGNORE INTO items (id,source_id,title,content,created_at,run_id) "
            "VALUES (?,?,?,?,?,?)",
            rows,
        )

    dst.commit()
    inserted = dst.execute("SELECT changes()").fetchone()[0]
    dst.close()

    print(f"archive: merged {len(rows)} rows ({inserted} new) → {ARCHIVE_DB.name}")
    return inserted


# ── Feed health ───────────────────────────────────────────────────────────────

HEALTH_GREEN = 14   # days
HEALTH_AMBER = 30   # days


def _parse_opml() -> list[tuple[str, str]]:
    """Return (feed_url, category) pairs from feed.opml."""
    tree  = ET.parse(OPML_PATH)
    feeds: list[tuple[str, str]] = []

    def walk(node: ET.Element, category: str = "") -> None:
        for child in node:
            if child.tag != "outline":
                continue
            url = child.attrib.get("xmlUrl", "")
            if url:
                feeds.append((url, category))
            else:
                walk(child, child.attrib.get("text", ""))

    body = tree.getroot().find("body")
    if body is not None:
        walk(body)

    return feeds


def feed_health() -> list[dict]:
    """
    Return one dict per feed in feed.opml:
      {url, category, total, last_seen (datetime|None), status, days_ago (int|None)}

    Requires archive.db to exist; returns empty list if it does not.
    """
    if not ARCHIVE_DB.exists():
        return []

    feeds = _parse_opml()
    conn  = sqlite3.connect(ARCHIVE_DB)
    now   = datetime.now(timezone.utc)
    result: list[dict] = []

    for url, category in feeds:
        row = conn.execute(
            """SELECT created_at
               FROM items
               WHERE source_id = ?
               ORDER BY created_at DESC
               LIMIT 1""",
            (url,),
        ).fetchone()

        total = conn.execute(
            "SELECT COUNT(*) FROM items WHERE source_id = ?", (url,)
        ).fetchone()[0]

        last_seen = None
        days_ago  = None
        status    = "grey"

        if row and row[0]:
            try:
                # created_at is stored as the feed's published string or run_id
                # Try ISO format first, then run_id format
                ts = row[0]
                try:
                    last_seen = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    last_seen = datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(
                        tzinfo=timezone.utc
                    )

                days_ago = (now - last_seen).days

                if   days_ago < HEALTH_GREEN: status = "green"
                elif days_ago < HEALTH_AMBER: status = "amber"
                else:                          status = "red"

            except Exception:
                pass

        result.append({
            "url":       url,
            "category":  category or "Uncategorized",
            "total":     total,
            "last_seen": last_seen,
            "days_ago":  days_ago,
            "status":    status,
        })

    conn.close()

    # Sort: red first, then amber, green, grey; then by days_ago desc
    _order = {"red": 0, "amber": 1, "grey": 2, "green": 3}
    result.sort(key=lambda r: (_order[r["status"]], -(r["days_ago"] or 9999)))

    return result


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    merge()


if __name__ == "__main__":
    main()
