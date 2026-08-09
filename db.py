"""Lakebase (PostgreSQL) connection + data-access layer.

Design goals
------------
* No hard-coded secrets. In the deployed Databricks App the Postgres password
  is a short-lived OAuth token minted at runtime via the Databricks SDK. For
  local development you may instead export ``PGPASSWORD`` with a token you
  generated yourself.
* Everything is driven by environment variables so the same code runs
  unchanged locally and inside Databricks Apps.
* Streamlit-agnostic: this module never imports Streamlit, so it can also be
  used by ``scripts/init_db.py``.

Environment variables
---------------------
LAKEBASE_INSTANCE_NAME  Lakebase database instance name (used to mint a token
                        and resolve the host when they aren't provided).
PGHOST                  Instance read/write DNS host. Optional; resolved from
                        the SDK if unset.
PGPORT                  Default 5432.
PGDATABASE              Default 'databricks_postgres'.
PGUSER                  Postgres role = a Databricks identity. Optional;
                        resolved from the SDK if unset.
PGPASSWORD              Optional. If set, used directly (local dev). Otherwise
                        a token is minted via the Databricks SDK.
PGSSLMODE               Default 'require'.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row

# --- allowed enum values, kept in sync with sql/schema.sql --------------------
STATUSES = ["open", "in_progress", "resolved", "closed"]
PRIORITIES = ["low", "medium", "high", "urgent"]
CATEGORIES = ["general", "access", "bug", "hardware", "billing", "feature"]


# =============================================================================
# Connection handling
# =============================================================================
def _resolve_credentials() -> dict[str, Any]:
    """Return psycopg connection kwargs, minting a token if needed."""
    host = os.getenv("PGHOST")
    user = os.getenv("PGUSER")
    password = os.getenv("PGPASSWORD")
    instance = os.getenv("LAKEBASE_INSTANCE_NAME")

    # If host / user / password aren't all supplied, ask the Databricks SDK.
    if not (host and user and password):
        if not instance:
            missing = "PGHOST/PGUSER/PGPASSWORD or LAKEBASE_INSTANCE_NAME"
            raise RuntimeError(
                f"Cannot build a Lakebase connection: set {missing}. "
                "In Databricks Apps, set LAKEBASE_INSTANCE_NAME (and attach the "
                "instance as a resource); locally, export PGHOST/PGUSER/PGPASSWORD."
            )
        from databricks.sdk import WorkspaceClient  # imported lazily

        w = WorkspaceClient()
        if not host:
            inst = w.database.get_database_instance(name=instance)
            # Attribute name has varied across SDK versions; try known ones.
            host = (
                getattr(inst, "read_write_dns", None)
                or getattr(inst, "dns_name", None)
                or getattr(inst, "read_only_dns", None)
            )
        if not user:
            user = w.current_user.me().user_name
        if not password:
            cred = w.database.generate_database_credential(
                request_id=str(uuid.uuid4()), instance_names=[instance]
            )
            password = cred.token

    return {
        "host": host,
        "port": os.getenv("PGPORT", "5432"),
        "dbname": os.getenv("PGDATABASE", "databricks_postgres"),
        "user": user,
        "password": password,
        "sslmode": os.getenv("PGSSLMODE", "require"),
    }


def get_connection() -> psycopg.Connection:
    """Open a fresh autocommit connection with dict rows."""
    kwargs = _resolve_credentials()
    return psycopg.connect(row_factory=dict_row, autocommit=True, **kwargs)


# A single long-lived connection is reused across Streamlit reruns (same
# process). Lakebase enforces token expiry only at login, so an already-open
# connection keeps working; we lazily reconnect if it ever drops.
_conn: Optional[psycopg.Connection] = None


def _connection() -> psycopg.Connection:
    global _conn
    if _conn is None or _conn.closed:
        _conn = get_connection()
    return _conn


def _run(query: str, params: Any = None, fetch: Optional[str] = None):
    """Execute a query with one automatic reconnect-and-retry."""
    global _conn
    last_err: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            with _connection().cursor() as cur:
                cur.execute(query, params)
                if fetch == "all":
                    return cur.fetchall()
                if fetch == "one":
                    return cur.fetchone()
                return None
        except psycopg.OperationalError as err:  # dropped connection, etc.
            last_err = err
            try:
                if _conn is not None:
                    _conn.close()
            except Exception:
                pass
            _conn = None
    raise last_err  # type: ignore[misc]


# =============================================================================
# Reads
# =============================================================================
def list_tickets(
    statuses: Optional[list[str]] = None,
    priorities: Optional[list[str]] = None,
    search: Optional[str] = None,
) -> list[dict]:
    """Return tickets (newest activity first) with message counts, filtered."""
    query = """
        SELECT
            t.*,
            COALESCE(m.cnt, 0)                 AS message_count,
            COALESCE(m.last_at, t.created_at)  AS last_activity
        FROM tickets t
        LEFT JOIN (
            SELECT ticket_id, count(*) AS cnt, max(created_at) AS last_at
            FROM ticket_messages
            GROUP BY ticket_id
        ) m ON m.ticket_id = t.ticket_id
        WHERE (%(statuses)s::text[]   IS NULL OR t.status   = ANY(%(statuses)s::text[]))
          AND (%(priorities)s::text[] IS NULL OR t.priority = ANY(%(priorities)s::text[]))
          AND (%(search)s::text       IS NULL OR t.title ILIKE %(search)s::text)
        ORDER BY t.updated_at DESC, t.ticket_id DESC
    """
    params = {
        "statuses": statuses or None,
        "priorities": priorities or None,
        "search": f"%{search.strip()}%" if search and search.strip() else None,
    }
    return _run(query, params, fetch="all") or []


def get_ticket(ticket_id: int) -> Optional[dict]:
    return _run(
        "SELECT * FROM tickets WHERE ticket_id = %s", (ticket_id,), fetch="one"
    )


def list_messages(ticket_id: int) -> list[dict]:
    return (
        _run(
            "SELECT * FROM ticket_messages WHERE ticket_id = %s "
            "ORDER BY created_at ASC, message_id ASC",
            (ticket_id,),
            fetch="all",
        )
        or []
    )


def get_stats() -> dict:
    """Aggregate counts for the dashboard tiles."""
    rows = _run("SELECT status, count(*) AS n FROM tickets GROUP BY status", fetch="all") or []
    by_status = {r["status"]: r["n"] for r in rows}
    prio_rows = _run("SELECT priority, count(*) AS n FROM tickets GROUP BY priority", fetch="all") or []
    by_priority = {r["priority"]: r["n"] for r in prio_rows}
    total = sum(by_status.values())
    return {
        "total": total,
        "open": by_status.get("open", 0),
        "in_progress": by_status.get("in_progress", 0),
        "resolved": by_status.get("resolved", 0),
        "closed": by_status.get("closed", 0),
        "by_status": by_status,
        "by_priority": by_priority,
    }


# =============================================================================
# Writes
# =============================================================================
def create_ticket(
    title: str,
    created_by: str,
    priority: str = "medium",
    category: str = "general",
    status: str = "open",
) -> int:
    row = _run(
        """
        INSERT INTO tickets (title, status, priority, category, created_by)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING ticket_id
        """,
        (title.strip(), status, priority, category, created_by),
        fetch="one",
    )
    return int(row["ticket_id"])


def add_message(ticket_id: int, message_text: str, author: str) -> int:
    row = _run(
        """
        INSERT INTO ticket_messages (ticket_id, message_text, author)
        VALUES (%s, %s, %s)
        RETURNING message_id
        """,
        (ticket_id, message_text.strip(), author),
        fetch="one",
    )
    # Bump the parent ticket's activity timestamp so it sorts to the top.
    _run("UPDATE tickets SET updated_at = now() WHERE ticket_id = %s", (ticket_id,))
    return int(row["message_id"])


def update_status(ticket_id: int, status: str) -> None:
    _run(
        "UPDATE tickets SET status = %s, updated_at = now() WHERE ticket_id = %s",
        (status, ticket_id),
    )


def delete_ticket(ticket_id: int) -> None:
    # ticket_messages rows are removed automatically (ON DELETE CASCADE).
    _run("DELETE FROM tickets WHERE ticket_id = %s", (ticket_id,))
