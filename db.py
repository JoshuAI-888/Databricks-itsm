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

import datetime
import os
import uuid
from typing import Any, Optional, Union

import psycopg
from psycopg.rows import dict_row

# --- allowed enum values, kept in sync with sql/schema.sql --------------------
STATUSES = ["open", "in_progress", "resolved", "closed"]
PRIORITIES = ["low", "medium", "high", "urgent"]
CATEGORIES = ["general", "access", "bug", "hardware", "billing", "feature"]

# Which timestamp column a date-range filter applies to. Keys double as the
# allow-list for `date_basis` params below (values are UI labels only).
DATE_BASES = {"created_at": "Date raised", "updated_at": "Last activity"}

DateLike = Union[datetime.datetime, datetime.date, None]


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
            # NOTE: only read/write endpoints are acceptable here. The instance
            # also exposes a read-only DNS name, and silently falling back to it
            # would leave the app able to read but failing every write with a
            # confusing "cannot execute INSERT in a read-only transaction".
            # Better to fail loudly and tell the operator to set PGHOST.
            host = getattr(inst, "read_write_dns", None) or getattr(inst, "dns_name", None)
            if not host:
                raise RuntimeError(
                    f"Could not determine the read/write hostname for Lakebase "
                    f"instance {instance!r} from the SDK. Set PGHOST explicitly to "
                    f"the instance's read/write DNS name (shown on its detail page). "
                    f"Do not use the read-only DNS name — writes will fail."
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
# Date-range filtering helpers
# =============================================================================
# `date_basis`, `grain`, and `dimension` (below) all end up interpolated straight
# into SQL as column/keyword identifiers -- Postgres has no way to bind those as
# parameters. Every one of them MUST be checked against a hard-coded allow-list
# before it touches an f-string; the values (dates, statuses, ...) still flow in
# as ordinary bound %(...)s params, same as the rest of this module.
_GRAIN_INTERVALS: dict[str, str] = {"day": "1 day", "week": "1 week", "month": "1 month"}
_DIMENSIONS = ("status", "priority", "category")


def _date_column(date_basis: str) -> str:
    """Validate `date_basis` against DATE_BASES and return it, safe to interpolate."""
    if date_basis not in DATE_BASES:
        raise ValueError(f"date_basis must be one of {sorted(DATE_BASES)}, got {date_basis!r}")
    return date_basis


def _normalize_date_range(date_from: DateLike, date_to: DateLike) -> tuple[DateLike, DateLike]:
    """Widen a bare `date` upper bound to end-of-day so the range stays inclusive.

    Callers may pass `datetime.date` (e.g. from a date-picker widget). A bare date
    for `date_to` means "through the end of that day" to a human, but compared
    naively against a timestamptz it would exclude everything after midnight --
    so we bump it to 23:59:59.999999 on that day. `date_from` needs no such
    adjustment since midnight is already its inclusive start.
    """
    if date_to is not None and not isinstance(date_to, datetime.datetime):
        date_to = datetime.datetime.combine(date_to, datetime.time.max)
    return date_from, date_to


def _date_predicate(
    date_basis: str,
    date_from: DateLike,
    date_to: DateLike,
    params: dict[str, Any],
    alias: str = "",
) -> str:
    """Build a WHERE-clause fragment restricting `<alias>.<date_basis col>` to the
    inclusive [date_from, date_to] range, and stash the bounds into `params`.

    Follows the module's existing "None means unfiltered" pattern (see
    `list_tickets`): either bound may be None to leave that side open. Mutates
    `params` in place so callers can build one clause and reuse it across
    several queries that share the same params dict.
    """
    col = _date_column(date_basis)
    date_from, date_to = _normalize_date_range(date_from, date_to)
    prefix = f"{alias}." if alias else ""
    params["date_from"] = date_from
    params["date_to"] = date_to
    return (
        f"(%(date_from)s::timestamptz IS NULL OR {prefix}{col} >= %(date_from)s::timestamptz) "
        f"AND (%(date_to)s::timestamptz IS NULL OR {prefix}{col} <= %(date_to)s::timestamptz)"
    )


# =============================================================================
# Reads
# =============================================================================
def list_tickets(
    statuses: Optional[list[str]] = None,
    priorities: Optional[list[str]] = None,
    search: Optional[str] = None,
    date_from: DateLike = None,
    date_to: DateLike = None,
    date_basis: str = "created_at",
) -> list[dict]:
    """Return tickets (newest activity first) with message counts, filtered.

    date_from/date_to bound `date_basis` ("created_at" or "updated_at"),
    inclusive of both ends; a bare `date` for date_to covers the whole day.
    Both default to None (unbounded), so existing callers are unaffected.
    """
    params: dict[str, Any] = {
        "statuses": statuses or None,
        "priorities": priorities or None,
        "search": f"%{search.strip()}%" if search and search.strip() else None,
    }
    date_clause = _date_predicate(date_basis, date_from, date_to, params, alias="t")
    query = f"""
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
          AND {date_clause}
        ORDER BY t.updated_at DESC, t.ticket_id DESC
    """
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


def get_stats(
    date_from: DateLike = None,
    date_to: DateLike = None,
    date_basis: str = "created_at",
) -> dict:
    """Aggregate counts for the dashboard tiles, optionally restricted to a date range.

    See `_date_predicate` for date_from/date_to/date_basis semantics. Defaults to
    unbounded (whole-table) stats, matching the previous no-argument behaviour.
    """
    params: dict[str, Any] = {}
    date_clause = _date_predicate(date_basis, date_from, date_to, params)
    rows = _run(
        f"SELECT status, count(*) AS n FROM tickets WHERE {date_clause} GROUP BY status",
        params,
        fetch="all",
    ) or []
    by_status = {r["status"]: r["n"] for r in rows}
    prio_rows = _run(
        f"SELECT priority, count(*) AS n FROM tickets WHERE {date_clause} GROUP BY priority",
        params,
        fetch="all",
    ) or []
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
# Reporting / analytics
# =============================================================================
def volume_over_time(
    date_from: DateLike = None,
    date_to: DateLike = None,
    date_basis: str = "created_at",
    grain: str = "day",
) -> list[dict]:
    """Ticket counts bucketed by day/week/month, zero-filled across the full range.

    Buckets are `date_trunc(grain, date_basis)`. When date_from is None the series
    starts at the earliest in-scope ticket; when date_to is None it ends at now().
    Empty buckets are zero-filled via generate_series + LEFT JOIN (rather than a
    plain GROUP BY) so a chart built from this has no gaps. Returns
    `[{"bucket": <date>, "n": <int>}, ...]` ascending by bucket; `[]` if there are
    no tickets in scope and date_from was left open (nothing to anchor the start).
    """
    if grain not in _GRAIN_INTERVALS:
        raise ValueError(f"grain must be one of {sorted(_GRAIN_INTERVALS)}, got {grain!r}")
    col = _date_column(date_basis)
    date_from, date_to = _normalize_date_range(date_from, date_to)
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "grain": grain,
        "step": _GRAIN_INTERVALS[grain],
    }
    query = f"""
        WITH scope AS (
            SELECT {col} AS ts
            FROM tickets
            WHERE (%(date_from)s::timestamptz IS NULL OR {col} >= %(date_from)s::timestamptz)
              AND (%(date_to)s::timestamptz   IS NULL OR {col} <= %(date_to)s::timestamptz)
        ),
        bounds AS (
            SELECT
                date_trunc(%(grain)s, COALESCE(%(date_from)s::timestamptz, MIN(ts))) AS lo,
                date_trunc(%(grain)s, COALESCE(%(date_to)s::timestamptz, now()))     AS hi
            FROM scope
        ),
        series AS (
            SELECT generate_series(lo, hi, %(step)s::interval) AS bucket
            FROM bounds
            WHERE lo IS NOT NULL
        ),
        counts AS (
            SELECT date_trunc(%(grain)s, ts) AS bucket, count(*) AS n
            FROM scope
            GROUP BY 1
        )
        SELECT s.bucket::date AS bucket, COALESCE(c.n, 0)::int AS n
        FROM series s
        LEFT JOIN counts c ON c.bucket = s.bucket
        ORDER BY s.bucket ASC
    """
    return _run(query, params, fetch="all") or []


def breakdown(
    dimension: str,
    date_from: DateLike = None,
    date_to: DateLike = None,
    date_basis: str = "created_at",
) -> list[dict]:
    """Ticket counts grouped by `dimension`, ordered by count desc then key asc.

    `dimension` must be "status", "priority", or "category" (validated against a
    hard-coded allow-list before being used as a column name -- see the note atop
    `_date_predicate`). Returns `[{"key": <str>, "n": <int>}, ...]`.
    """
    if dimension not in _DIMENSIONS:
        raise ValueError(f"dimension must be one of {_DIMENSIONS}, got {dimension!r}")
    params: dict[str, Any] = {}
    date_clause = _date_predicate(date_basis, date_from, date_to, params)
    query = f"""
        SELECT {dimension} AS key, count(*) AS n
        FROM tickets
        WHERE {date_clause}
        GROUP BY {dimension}
        ORDER BY n DESC, key ASC
    """
    return _run(query, params, fetch="all") or []


def resolution_stats(
    date_from: DateLike = None,
    date_to: DateLike = None,
    date_basis: str = "created_at",
) -> dict:
    """Approximate resolution-time percentiles for resolved/closed tickets.

    CAVEAT -- there is no `resolved_at` column in the schema, so "resolution time"
    here is only ever approximated as `updated_at - created_at` for tickets whose
    *current* status is 'resolved' or 'closed'. `updated_at` is bumped by any
    activity (a new message, a status change, ...), not specifically the moment a
    ticket became resolved, so this can over- or under-state true resolution time
    -- treat these numbers as directional, not exact.

    Returns `{"resolved_count": int, "median_hours": float|None,
    "avg_hours": float|None, "p90_hours": float|None}`; the float fields are hours
    rounded to 1 decimal, or None when there are no qualifying rows.
    """
    params: dict[str, Any] = {"resolved_statuses": ["resolved", "closed"]}
    date_clause = _date_predicate(date_basis, date_from, date_to, params)
    query = f"""
        SELECT
            count(*) AS resolved_count,
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (updated_at - created_at)) / 3600.0
            ) AS median_hours,
            avg(EXTRACT(EPOCH FROM (updated_at - created_at)) / 3600.0) AS avg_hours,
            percentile_cont(0.9) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (updated_at - created_at)) / 3600.0
            ) AS p90_hours
        FROM tickets
        WHERE status = ANY(%(resolved_statuses)s::text[])
          AND {date_clause}
    """
    row = _run(query, params, fetch="one") or {}

    def _round(v: Any) -> Optional[float]:
        return round(float(v), 1) if v is not None else None

    return {
        "resolved_count": int(row.get("resolved_count") or 0),
        "median_hours": _round(row.get("median_hours")),
        "avg_hours": _round(row.get("avg_hours")),
        "p90_hours": _round(row.get("p90_hours")),
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
