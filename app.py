"""Milford Support Desk — a Lakebase-backed Databricks App.

Users can browse support tickets, read/add messages, create tickets, update
status, and delete tickets. All data lives in Lakebase (PostgreSQL); nothing
is stored in memory.
"""

from __future__ import annotations

import html
from datetime import date, datetime, time, timedelta, timezone

import streamlit as st

import db
import theme

# =============================================================================
# Page setup
# =============================================================================
st.set_page_config(
    page_title="Milford Support Desk",
    page_icon="🛎️",
    layout="wide",
    initial_sidebar_state="collapsed",
)
theme.inject()

st.session_state.setdefault("selected_ticket_id", None)

# =============================================================================
# Reporting constants
# =============================================================================
PERIOD_OPTIONS = [
    "Last 7 days",
    "Last 30 days",
    "Last 90 days",
    "This month",
    "This quarter",
    "This year",
    "All time",
    "Custom…",
]
DEFAULT_PERIOD = "Last 30 days"


# =============================================================================
# Helpers
# =============================================================================
def current_user() -> str:
    """Identify the signed-in user from Databricks Apps auth headers.

    Databricks Apps forwards the end user's identity in request headers. We
    fall back to DEV_USER (local dev) or a guest label.
    """
    import os

    try:
        headers = st.context.headers or {}
    except Exception:
        headers = {}
    for key in ("X-Forwarded-Email", "X-Forwarded-Preferred-Username", "X-Forwarded-User"):
        val = headers.get(key) or headers.get(key.lower())
        if val:
            return val
    return os.getenv("DEV_USER", "guest@milford.co.nz")


def humanize(ts) -> str:
    """Short relative time, e.g. '3h ago'."""
    if ts is None:
        return ""
    if isinstance(ts, str):
        return ts
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    secs = (now - ts).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    days = int(secs // 86400)
    return f"{days}d ago" if days < 30 else ts.strftime("%d %b %Y")


def esc(text) -> str:
    return html.escape(str(text)) if text is not None else ""


def _fmt_date_range(d1: date, d2: date) -> str:
    """Short human range for a custom period, e.g. '1 Jul – 9 Aug 2026'."""
    if d1.year == d2.year and d1.month == d2.month:
        return f"{d1:%-d} – {d2:%-d %b %Y}"
    if d1.year == d2.year:
        return f"{d1:%-d %b} – {d2:%-d %b %Y}"
    return f"{d1:%-d %b %Y} – {d2:%-d %b %Y}"


def resolve_period(
    choice: str, custom_from: date | None, custom_to: date | None
) -> tuple[datetime | None, datetime | None, str]:
    """Turn a period preset (+ optional custom range) into a (from, to, label) triple.

    `from`/`to` are timezone-aware UTC datetimes ready to hand straight to
    db.* queries (None = unbounded, only for "All time"). Falls back to the
    last 30 days on an invalid or not-yet-chosen custom range, rather than
    crashing or querying garbage.
    """
    now = datetime.now(timezone.utc)
    fallback_from, fallback_to = now - timedelta(days=30), now

    if choice == "Last 7 days":
        return now - timedelta(days=7), now, choice
    if choice == "Last 30 days":
        return now - timedelta(days=30), now, choice
    if choice == "Last 90 days":
        return now - timedelta(days=90), now, choice
    if choice == "This month":
        return datetime(now.year, now.month, 1, tzinfo=timezone.utc), now, choice
    if choice == "This quarter":
        q_start_month = (now.month - 1) // 3 * 3 + 1
        return datetime(now.year, q_start_month, 1, tzinfo=timezone.utc), now, choice
    if choice == "This year":
        return datetime(now.year, 1, 1, tzinfo=timezone.utc), now, choice
    if choice == "All time":
        return None, None, choice

    # Custom… — not yet initialised (widgets render below this point) falls
    # back quietly; a genuinely inverted range warns before falling back.
    if custom_from is None or custom_to is None:
        return fallback_from, fallback_to, "Last 30 days"
    if custom_from > custom_to:
        st.warning("The custom range's From date is after To — showing the last 30 days instead.")
        return fallback_from, fallback_to, "Last 30 days"
    return (
        datetime.combine(custom_from, time.min, tzinfo=timezone.utc),
        datetime.combine(custom_to, time.max, tzinfo=timezone.utc),
        _fmt_date_range(custom_from, custom_to),
    )


USER = current_user()


# =============================================================================
# Dialogs (modals)
# =============================================================================
@st.dialog("Create a new ticket")
def new_ticket_dialog():
    st.caption("Describe the issue. Fields marked * are required.")
    title = st.text_input("Title *", max_chars=200, placeholder="Short summary of the issue")
    col1, col2 = st.columns(2)
    priority = col1.selectbox("Priority", db.PRIORITIES, index=db.PRIORITIES.index("medium"))
    category = col2.selectbox("Category", db.CATEGORIES, index=0)
    first_msg = st.text_area(
        "First message (optional)", max_chars=2000,
        placeholder="Add any detail that will help whoever picks this up.",
    )

    if st.button("Create ticket", type="primary", use_container_width=True):
        clean_title = (title or "").strip()
        if len(clean_title) < 3:
            st.error("Please enter a title of at least 3 characters.")
            return
        try:
            ticket_id = db.create_ticket(
                title=clean_title, created_by=USER, priority=priority, category=category
            )
            if first_msg and first_msg.strip():
                db.add_message(ticket_id, first_msg, USER)
        except Exception as err:  # surface DB errors gracefully
            st.error(f"Could not create the ticket: {err}")
            return
        st.session_state.selected_ticket_id = ticket_id
        st.session_state["_toast"] = ("Ticket created ✓", "🎫")
        st.rerun()


@st.dialog("Delete ticket")
def delete_ticket_dialog(ticket: dict):
    st.warning(
        f"This permanently deletes ticket **#{ticket['ticket_id']} — "
        f"{esc(ticket['title'])}** and all of its messages. This cannot be undone."
    )
    confirm = st.checkbox("Yes, I understand and want to delete this ticket.")
    col1, col2 = st.columns(2)
    if col1.button("Cancel", use_container_width=True):
        st.rerun()
    if col2.button("Delete permanently", type="primary", use_container_width=True, disabled=not confirm):
        try:
            db.delete_ticket(ticket["ticket_id"])
        except Exception as err:
            st.error(f"Could not delete the ticket: {err}")
            return
        st.session_state.selected_ticket_id = None
        st.session_state["_toast"] = ("Ticket deleted", "🗑️")
        st.rerun()


# =============================================================================
# Header
# =============================================================================
def render_header():
    st.markdown(
        f"""
        <div class="mf-glass mf-header">
          <div class="mf-brand">
            <div class="mf-logo">M</div>
            <div>
              <div class="mf-title">Milford Support Desk</div>
              <div class="mf-subtitle">Internal IT &amp; operations support · powered by Lakebase</div>
            </div>
          </div>
          <div class="mf-user"><span class="dot"></span>{esc(USER)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# Stats dashboard
# =============================================================================
def render_stats(stats: dict, period_label: str, basis_label: str):
    verb = {"Date raised": "Tickets raised", "Last activity": "Tickets active"}.get(
        basis_label, "Tickets"
    )
    st.caption(f"{verb} · {period_label}")

    tiles = [
        ("Total tickets", stats["total"], theme.SLATE),
        ("Open", stats["open"], theme.BLUE),
        ("In progress", stats["in_progress"], theme.AMBER),
        ("Resolved", stats["resolved"], theme.GREEN),
    ]
    cols = st.columns(4, gap="medium")
    for col, (label, value, color) in zip(cols, tiles):
        col.markdown(
            f"""
            <div class="mf-glass mf-stat">
              <div class="label">{label}</div>
              <div class="value">{value}</div>
              <div class="accent" style="background:{color}"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Status distribution bar
    total = max(stats["total"], 1)
    segments, legend = "", ""
    for status in db.STATUSES:
        n = stats["by_status"].get(status, 0)
        if n == 0:
            continue
        color = theme.STATUS_COLORS[status]
        pct = n / total * 100
        segments += f'<span style="width:{pct:.1f}%;background:{color}"></span>'
        legend += (
            f'<span class="k"><span class="sw" style="background:{color}"></span>'
            f'{theme.STATUS_LABELS[status]} · {n}</span>'
        )
    st.markdown(
        f"""
        <div class="mf-glass" style="padding:16px 18px;margin-top:14px">
          <div class="label" style="font-size:12px;color:{theme.MUTED};
               text-transform:uppercase;letter-spacing:0.06em;font-weight:600;
               margin-bottom:10px">Status distribution · {esc(period_label)}</div>
          <div class="mf-distbar">{segments or '<span style="width:100%;background:#e9edee"></span>'}</div>
          <div class="mf-legend">{legend or 'No tickets yet'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# Reporting
# =============================================================================
def _bucket_label(bucket, grain: str) -> str:
    """Format a volume_over_time bucket for the chart axis, per grain."""
    if isinstance(bucket, str):
        return bucket
    if grain == "day":
        return bucket.strftime("%d %b")
    if grain == "week":
        return f"w/o {bucket.strftime('%d %b')}"
    return bucket.strftime("%b %Y")


def _auto_grain(date_from, date_to) -> str:
    """Pick a bucket size from the period length; open-ended/unknown -> month."""
    if date_from is None or date_to is None:
        return "month"
    days = (date_to - date_from).days
    if days <= 31:
        return "day"
    if days <= 180:
        return "week"
    return "month"


def _fmt_duration(hours) -> str:
    """Render an hour count as 'X.X days' above 48h, else 'X.X hrs'."""
    if hours is None:
        return "—"
    if hours >= 48:
        return f"{hours / 24:.1f} days"
    return f"{hours:.1f} hrs"


def _render_hbar_card(title: str, items: list[dict], color_of, empty_msg: str):
    """A ranked horizontal-bar card in the mf-glass style, shared by both breakdowns."""
    if not items:
        st.markdown(
            f'<div class="mf-glass mf-empty" style="padding:28px 18px">'
            f'<div class="big">{esc(title)}</div>{esc(empty_msg)}</div>',
            unsafe_allow_html=True,
        )
        return

    peak = max(i["n"] for i in items) or 1
    rows = ""
    for i in items:
        pct = i["n"] / peak * 100
        color = color_of(i["key"])
        label = esc(str(i["key"]).replace("_", " ").capitalize())
        rows += f"""
        <div style="display:flex;align-items:center;gap:10px;margin-top:10px">
          <div style="width:96px;flex:0 0 auto;font-size:12.5px;font-weight:600;
               color:{theme.SLATE_2};white-space:nowrap;overflow:hidden;
               text-overflow:ellipsis" title="{label}">{label}</div>
          <div style="flex:1 1 auto;height:10px;border-radius:999px;
               background:{theme.CLOUD};overflow:hidden">
            <div style="width:{pct:.1f}%;height:100%;border-radius:999px;
                 background:{color}"></div>
          </div>
          <div style="width:30px;flex:0 0 auto;text-align:right;font-size:12.5px;
               font-weight:700;color:{theme.SLATE}">{i["n"]}</div>
        </div>
        """
    st.markdown(
        f"""
        <div class="mf-glass" style="padding:16px 18px">
          <div class="label" style="font-size:12px;color:{theme.MUTED};
               text-transform:uppercase;letter-spacing:0.06em;font-weight:600;
               margin-bottom:6px">{esc(title)}</div>
          {rows}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_reporting(date_from, date_to, date_basis: str, period_label: str):
    """Aggregate reporting for the active period: volume trend, breakdowns, resolution time.

    Each panel wraps its own db call so one failing query only takes down
    that panel, and each degrades to a friendly empty state with no data.
    """
    with st.expander("📊 Reporting", expanded=False):
        st.caption(f"Scoped to {period_label} · {db.DATE_BASES.get(date_basis, date_basis)}")

        # --- Volume over time -------------------------------------------------
        st.markdown("**Volume over time**")
        grain = _auto_grain(date_from, date_to)
        try:
            volume = db.volume_over_time(
                date_from=date_from, date_to=date_to, date_basis=date_basis, grain=grain
            )
        except Exception as err:
            st.error(f"Couldn't load ticket volume: {err}")
        else:
            if not volume or not any(r["n"] for r in volume):
                st.markdown(
                    '<div class="mf-glass mf-empty"><div class="big">No tickets in this period</div>'
                    "Widen the period to see a volume trend.</div>",
                    unsafe_allow_html=True,
                )
            else:
                grain_col = {"day": "Day", "week": "Week starting", "month": "Month"}[grain]
                chart_data = {
                    grain_col: [_bucket_label(r["bucket"], grain) for r in volume],
                    "Tickets": [r["n"] for r in volume],
                }
                st.bar_chart(
                    chart_data, x=grain_col, y="Tickets", color=theme.ORANGE,
                    use_container_width=True,
                )
                st.caption(f"Bucketed by {grain}.")

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        # --- Breakdowns: category / priority -----------------------------------
        b1, b2 = st.columns(2, gap="medium")
        with b1:
            try:
                cat_rows = db.breakdown(
                    "category", date_from=date_from, date_to=date_to, date_basis=date_basis
                )
            except Exception as err:
                st.error(f"Couldn't load the category breakdown: {err}")
            else:
                _render_hbar_card(
                    "By category", cat_rows, lambda _k: theme.PURPLE,
                    "No tickets in this period.",
                )
        with b2:
            try:
                pri_rows = db.breakdown(
                    "priority", date_from=date_from, date_to=date_to, date_basis=date_basis
                )
            except Exception as err:
                st.error(f"Couldn't load the priority breakdown: {err}")
            else:
                _render_hbar_card(
                    "By priority", pri_rows,
                    lambda k: theme.PRIORITY_COLORS.get(k, theme.MUTED),
                    "No tickets in this period.",
                )

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        # --- Resolution time -----------------------------------------------------
        st.markdown("**Resolution time**")
        try:
            res = db.resolution_stats(date_from=date_from, date_to=date_to, date_basis=date_basis)
        except Exception as err:
            st.error(f"Couldn't load resolution stats: {err}")
        else:
            if not res or not res.get("resolved_count"):
                st.markdown(
                    '<div class="mf-glass mf-empty"><div class="big">No resolved tickets in this period</div>'
                    "Resolution time appears once tickets are marked resolved.</div>",
                    unsafe_allow_html=True,
                )
            else:
                tiles = [
                    ("Resolved", str(res["resolved_count"]), theme.GREEN),
                    ("Median", _fmt_duration(res.get("median_hours")), theme.BLUE),
                    ("Average", _fmt_duration(res.get("avg_hours")), theme.AMBER),
                    ("P90", _fmt_duration(res.get("p90_hours")), theme.PURPLE),
                ]
                cols = st.columns(4, gap="medium")
                for col, (label, shown, color) in zip(cols, tiles):
                    col.markdown(
                        f"""
                        <div class="mf-glass mf-stat">
                          <div class="label">{label}</div>
                          <div class="value">{shown}</div>
                          <div class="accent" style="background:{color}"></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.caption(
                    "⚠ Approximate — there is no dedicated resolved-at timestamp, so this is "
                    "measured as last activity minus created. Treat it as indicative, not exact."
                )


# =============================================================================
# Ticket list
# =============================================================================
def render_ticket_list(tickets: list[dict]):
    st.markdown("#### Tickets")
    if not tickets:
        st.markdown(
            '<div class="mf-glass mf-empty"><div class="big">No tickets match your filters</div>'
            "Try clearing the search or status filters.</div>",
            unsafe_allow_html=True,
        )
        return

    for t in tickets:
        selected = t["ticket_id"] == st.session_state.selected_ticket_id
        with st.container(border=True):
            top = st.columns([0.78, 0.22])
            top[0].markdown(
                f'<div class="mf-ticket-title">#{t["ticket_id"]} · {esc(t["title"])}</div>',
                unsafe_allow_html=True,
            )
            if top[1].button(
                "Viewing" if selected else "View",
                key=f"view_{t['ticket_id']}",
                type="primary" if selected else "secondary",
                use_container_width=True,
            ):
                st.session_state.selected_ticket_id = t["ticket_id"]
                st.rerun()
            st.markdown(
                theme.status_badge(t["status"])
                + " " + theme.priority_badge(t["priority"])
                + " " + theme.category_badge(t["category"])
                + f'<span class="mf-meta">&nbsp;·&nbsp;{t["message_count"]} '
                f'message{"s" if t["message_count"] != 1 else ""} · '
                f'updated {humanize(t["last_activity"])} · by {esc(t["created_by"])}</span>',
                unsafe_allow_html=True,
            )


# =============================================================================
# Ticket detail
# =============================================================================
def render_detail():
    ticket_id = st.session_state.selected_ticket_id
    if ticket_id is None:
        st.markdown("#### Ticket detail")
        st.markdown(
            '<div class="mf-glass mf-empty"><div class="big">Select a ticket</div>'
            "Choose a ticket on the left to view its conversation and manage it.</div>",
            unsafe_allow_html=True,
        )
        return

    ticket = db.get_ticket(ticket_id)
    if ticket is None:  # was deleted elsewhere
        st.session_state.selected_ticket_id = None
        st.info("That ticket no longer exists. Pick another from the list.")
        return

    st.markdown("#### Ticket detail")
    with st.container(border=True):
        st.markdown(
            f'<div style="font-size:18px;font-weight:700;color:{theme.SLATE}">'
            f'#{ticket["ticket_id"]} · {esc(ticket["title"])}</div>'
            + theme.status_badge(ticket["status"])
            + " " + theme.priority_badge(ticket["priority"])
            + " " + theme.category_badge(ticket["category"])
            + f'<div class="mf-meta" style="margin-top:8px">Opened by '
            f'{esc(ticket["created_by"])} · {humanize(ticket["created_at"])}</div>',
            unsafe_allow_html=True,
        )

        st.divider()

        # --- Manage: status update + delete ---------------------------------
        mcol1, mcol2, mcol3 = st.columns([0.5, 0.24, 0.26])
        new_status = mcol1.selectbox(
            "Status",
            db.STATUSES,
            index=db.STATUSES.index(ticket["status"]),
            format_func=lambda s: theme.STATUS_LABELS[s],
            key=f"status_{ticket_id}",
        )
        mcol2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if mcol2.button("Update", use_container_width=True, key=f"upd_{ticket_id}"):
            if new_status != ticket["status"]:
                db.update_status(ticket_id, new_status)
                st.session_state["_toast"] = (f"Status → {theme.STATUS_LABELS[new_status]}", "🔄")
                st.rerun()
            else:
                st.toast("Status unchanged")
        mcol3.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if mcol3.button("Delete", use_container_width=True, key=f"del_{ticket_id}"):
            delete_ticket_dialog(ticket)

        st.divider()

        # --- Conversation ---------------------------------------------------
        st.markdown("**Conversation**")
        messages = db.list_messages(ticket_id)
        if not messages:
            st.caption("No messages yet — add the first one below.")
        for m in messages:
            st.markdown(
                f"""
                <div class="mf-msg">
                  <div style="display:flex;justify-content:space-between;align-items:baseline">
                    <span class="who">{esc(m["author"])}</span>
                    <span class="when">{humanize(m["created_at"])}</span>
                  </div>
                  <div class="body">{esc(m["message_text"])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # --- Add message ----------------------------------------------------
        with st.form(f"msg_form_{ticket_id}", clear_on_submit=True):
            text = st.text_area(
                "Add a message", max_chars=2000, placeholder="Write a reply…",
                label_visibility="collapsed",
            )
            if st.form_submit_button("Send message", type="primary"):
                if not text or not text.strip():
                    st.error("Message can't be empty.")
                else:
                    db.add_message(ticket_id, text, USER)
                    st.session_state["_toast"] = ("Message added", "💬")
                    st.rerun()


# =============================================================================
# Main
# =============================================================================
def main():
    # flush any queued toast from the previous run
    if "_toast" in st.session_state:
        msg, icon = st.session_state.pop("_toast")
        st.toast(msg, icon=icon)

    render_header()

    # Resolve the active reporting period from widget state set on a prior run
    # (the period picker itself lives inside the toolbar, rendered below the
    # stats it feeds — Streamlit persists widget values in session_state
    # across reruns, so this read reflects the latest choice even though the
    # widgets that write it are instantiated further down the script).
    period_choice = st.session_state.get("period_choice", DEFAULT_PERIOD)
    date_basis = st.session_state.get("date_basis", "created_at")
    date_from, date_to, period_label = resolve_period(
        period_choice,
        st.session_state.get("period_from"),
        st.session_state.get("period_to"),
    )
    basis_label = db.DATE_BASES.get(date_basis, date_basis)

    try:
        stats = db.get_stats(date_from=date_from, date_to=date_to, date_basis=date_basis)
    except Exception as err:
        st.error(
            "Couldn't reach Lakebase. Check that the database instance is running "
            "and the app's environment variables / grants are set (see DEPLOY.md)."
        )
        st.exception(err)
        st.stop()

    render_stats(stats, period_label, basis_label)

    # --- Toolbar: filters + period + new ticket ------------------------------
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns([0.3, 0.3, 0.24, 0.16])
        status_filter = f1.multiselect(
            "Status", db.STATUSES, format_func=lambda s: theme.STATUS_LABELS[s],
            placeholder="All statuses",
        )
        priority_filter = f2.multiselect(
            "Priority", db.PRIORITIES, format_func=str.capitalize, placeholder="All priorities",
        )
        search = f3.text_input("Search", placeholder="Search title…")
        f4.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if f4.button("＋ New ticket", type="primary", use_container_width=True):
            new_ticket_dialog()

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # Row 2 only makes room for From/To when "Custom…" is selected, so the
        # toolbar stays compact for the common presets.
        show_custom = st.session_state.get("period_choice", DEFAULT_PERIOD) == "Custom…"
        if show_custom:
            g1, g2, g3, g4 = st.columns([0.22, 0.19, 0.19, 0.40])
        else:
            g1, g4 = st.columns([0.32, 0.68])
            g2 = g3 = None

        g1.selectbox(
            "Period", PERIOD_OPTIONS,
            index=PERIOD_OPTIONS.index(DEFAULT_PERIOD),
            key="period_choice",
            help="Which window of tickets the stats, reporting and list below cover.",
        )
        if g2 is not None:
            default_to = datetime.now(timezone.utc).date()
            default_from = default_to - timedelta(days=30)
            g2.date_input("From", value=default_from, key="period_from")
            g3.date_input("To", value=default_to, key="period_to")

        g4.segmented_control(
            "Date basis",
            options=list(db.DATE_BASES.keys()),
            format_func=lambda k: db.DATE_BASES[k],
            default="created_at",
            selection_mode="single",
            key="date_basis",
            help=(
                "Date raised keeps a ticket fixed to the period it was created in — "
                "stable for period-over-period reporting. Last activity moves a "
                "ticket between periods every time it's touched."
            ),
        )

    render_reporting(date_from, date_to, date_basis, period_label)

    tickets = db.list_tickets(
        statuses=status_filter or None,
        priorities=priority_filter or None,
        search=search or None,
        date_from=date_from,
        date_to=date_to,
        date_basis=date_basis,
    )

    left, right = st.columns([0.46, 0.54], gap="large")
    with left:
        render_ticket_list(tickets)
    with right:
        render_detail()


if __name__ == "__main__":
    main()
