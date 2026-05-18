from __future__ import annotations

import sqlite3
from pathlib import Path


DB_PATH = Path("data/emergyx_care.db")


def print_table(cursor: sqlite3.Cursor, table_name: str) -> None:
    print(f"\n== {table_name} ==")
    try:
        rows = cursor.execute(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT 20").fetchall()
    except sqlite3.OperationalError as exc:
        print(f"Skipping {table_name}: {exc}")
        return

    for row in rows:
        print(row)


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    for table_name in ("events", "alerts", "agent_decisions", "daily_reports"):
        print_table(cursor, table_name)
    connection.close()


if __name__ == "__main__":
    main()
