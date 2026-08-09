"""Milford Support Desk — a Lakebase-backed Databricks App.

Users can browse support tickets, read/add messages, create tickets, update
status, and delete tickets. All data lives in Lakebase (PostgreSQL); nothing
is stored in memory.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

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
def render_stats(stats: dict):
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
               margin-bottom:10px">Status distribution</div>
          <div class="mf-distbar">{segments or '<span style="width:100%;background:#e9edee"></span>'}</div>
          <div class="mf-legend">{legend or 'No tickets yet'}</div>
        </div>
        """,
        unsafe_allow_html=True,
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

    try:
        stats = db.get_stats()
    except Exception as err:
        st.error(
            "Couldn't reach Lakebase. Check that the database instance is running "
            "and the app's environment variables / grants are set (see DEPLOY.md)."
        )
        st.exception(err)
        st.stop()

    render_stats(stats)

    # --- Toolbar: filters + new ticket --------------------------------------
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

    tickets = db.list_tickets(
        statuses=status_filter or None,
        priorities=priority_filter or None,
        search=search or None,
    )

    left, right = st.columns([0.46, 0.54], gap="large")
    with left:
        render_ticket_list(tickets)
    with right:
        render_detail()


if __name__ == "__main__":
    main()
