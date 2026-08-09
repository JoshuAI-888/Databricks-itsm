"""Create the schema and load sample data into Lakebase.

Run this once during setup (see DEPLOY.md, step 4). It reads the SQL files in
../sql and executes them against the database resolved from your environment
variables (the same ones the app uses).

Usage:
    pip install -r requirements.txt
    export LAKEBASE_INSTANCE_NAME=... PGHOST=... PGDATABASE=... \
           PGUSER=<you> PGPASSWORD=<oauth-token>
    python scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable so we can reuse db.get_connection().
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402

SQL_DIR = ROOT / "sql"


def run_sql_file(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    print(f"  → executing {path.name} ...", end=" ", flush=True)
    with conn.cursor() as cur:
        cur.execute(sql)
    print("ok")


def main() -> int:
    print("Connecting to Lakebase ...")
    try:
        conn = db.get_connection()
    except Exception as err:
        print(f"\nConnection failed: {err}", file=sys.stderr)
        print("Check your PG* / LAKEBASE_INSTANCE_NAME environment variables.", file=sys.stderr)
        return 1

    try:
        print("Applying schema and sample data:")
        run_sql_file(conn, SQL_DIR / "schema.sql")
        run_sql_file(conn, SQL_DIR / "seed_data.sql")

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM tickets")
            tickets = cur.fetchone()["n"]
            cur.execute("SELECT count(*) AS n FROM ticket_messages")
            messages = cur.fetchone()["n"]
        print(f"\nDone. {tickets} tickets and {messages} messages are in Lakebase.")
        return 0
    except Exception as err:
        print(f"\nSetup failed: {err}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
