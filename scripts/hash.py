from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "current.db"
SCHEMA_PATH = ROOT / "schema.sql"


def main():
    schema = SCHEMA_PATH.read_text("utf-8")

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
