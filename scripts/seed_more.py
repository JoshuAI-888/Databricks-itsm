"""Add 50 more sample tickets spread over the last ~12 months.

This exists so the reporting views have enough history to be worth looking at.
Unlike ``scripts/init_db.py`` this is **additive and re-runnable**: it never
truncates, and each ticket is inserted only if no ticket with the same title
exists yet, so running it twice is a no-op.

Usage (same environment variables as the app -- see DEPLOY.md section 4):
    export LAKEBASE_INSTANCE_NAME=...
    python scripts/seed_more.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable so we can reuse db.get_connection().
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402

SQL_FILE = ROOT / "sql" / "seed_more_tickets.sql"


def main() -> int:
    print("Connecting to Lakebase ...")
    try:
        conn = db.get_connection()
    except Exception as err:
        print(f"\nConnection failed: {err}", file=sys.stderr)
        print("Check your PG* / LAKEBASE_INSTANCE_NAME environment variables.", file=sys.stderr)
        return 1

    try:
        before = _counts(conn)
        print(f"  before: {before[0]} tickets, {before[1]} messages")
        print(f"  → executing {SQL_FILE.name} ...", end=" ", flush=True)
        with conn.cursor() as cur:
            cur.execute(SQL_FILE.read_text(encoding="utf-8"))
        print("ok")

        after = _counts(conn)
        added_t, added_m = after[0] - before[0], after[1] - before[1]
        if added_t == 0:
            print("\nNothing to do — these sample tickets are already loaded.")
        else:
            print(f"\nAdded {added_t} tickets and {added_m} messages.")
        print(f"Totals now: {after[0]} tickets, {after[1]} messages.")
        return 0
    except Exception as err:
        print(f"\nSeeding failed: {err}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def _counts(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM tickets")
        tickets = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM ticket_messages")
        messages = cur.fetchone()["n"]
    return tickets, messages


if __name__ == "__main__":
    raise SystemExit(main())
