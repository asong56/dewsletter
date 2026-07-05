from pathlib import Path
import sqlite3

from db_write import migrate

ROOT        = Path(__file__).resolve().parent.parent
DB_PATH     = ROOT / "current.db"
SCHEMA_PATH = ROOT / "schema.sql"


def main() -> None:
    schema = SCHEMA_PATH.read_text("utf-8")
    conn   = sqlite3.connect(DB_PATH)
    conn.executescript(schema)
    conn.commit()
    migrate(conn)
    conn.close()


if __name__ == "__main__":
    main()
