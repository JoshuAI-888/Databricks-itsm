"""Milford-branded 'liquid glass' theme for the Streamlit app.

Palette is Milford's corporate scheme (slate / orange / cloud + product
colours) applied as a modern-SaaS glassmorphism UI: frosted translucent
cards, soft shadows, a blurred colour-wash background.
"""

import html

import streamlit as st

# --- Milford palette ---------------------------------------------------------
SLATE = "#303c42"        # primary text / headings
SLATE_2 = "#46545b"      # secondary
MUTED = "#77858d"        # metadata / captions
CLOUD = "#eef1f2"        # panels
PAPER = "#ffffff"
ORANGE = "#e1690e"       # primary accent / focus
BORDER = "#dce2e4"
BLUE = "#1c99d6"         # KiwiSaver blue
GREEN = "#198754"        # success
AMBER = "#f3a83b"        # warning
DANGER = "#c94b42"       # danger
PURPLE = "#915fb4"       # wealth purple

STATUS_COLORS = {
    "open": BLUE,
    "in_progress": AMBER,
    "resolved": GREEN,
    "closed": MUTED,
}
STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "resolved": "Resolved",
    "closed": "Closed",
}
PRIORITY_COLORS = {
    "low": MUTED,
    "medium": BLUE,
    "high": ORANGE,
    "urgent": DANGER,
}


def inject() -> None:
    """Inject the global CSS. Call once, right after set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


def badge(text: str, color: str, *, solid: bool = False) -> str:
    """Return an HTML pill badge."""
    text = html.escape(str(text))
    if solid:
        return (
            f'<span class="mf-badge" style="background:{color};color:#fff;'
            f'border-color:{color}">{text}</span>'
        )
    return (
        f'<span class="mf-badge" style="color:{color};'
        f'background:{color}1a;border-color:{color}55">{text}</span>'
    )


def status_badge(status: str) -> str:
    return badge(STATUS_LABELS.get(status, status), STATUS_COLORS.get(status, MUTED), solid=True)


def priority_badge(priority: str) -> str:
    return badge(priority.capitalize(), PRIORITY_COLORS.get(priority, MUTED))


def category_badge(category: str) -> str:
    return badge(category.capitalize(), PURPLE)


_CSS = f"""
<style>
:root {{
  --slate:{SLATE}; --slate2:{SLATE_2}; --muted:{MUTED}; --cloud:{CLOUD};
  --orange:{ORANGE}; --border:{BORDER}; --blue:{BLUE}; --green:{GREEN};
}}

/* ---- Background: soft cloud wash with blurred colour blobs -------------- */
.stApp {{
  background:
    radial-gradient(1100px 600px at 8% -5%, rgba(225,105,14,0.10), transparent 60%),
    radial-gradient(1000px 620px at 100% 0%, rgba(28,153,214,0.12), transparent 55%),
    linear-gradient(180deg, #f6f8f9 0%, #eef1f2 100%);
  background-attachment: fixed;
  color: var(--slate);
  font-family: "Montserrat", -apple-system, BlinkMacSystemFont, "Segoe UI",
               Roboto, Helvetica, Arial, sans-serif;
}}

/* Hide Streamlit chrome for a cleaner app feel */
[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1280px; }}

h1, h2, h3, h4 {{ color: var(--slate); font-weight: 600; letter-spacing: -0.01em; }}

/* ---- Glass surface (reused everywhere) --------------------------------- */
.mf-glass {{
  background: rgba(255,255,255,0.58);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  backdrop-filter: blur(18px) saturate(140%);
  border: 1px solid rgba(255,255,255,0.65);
  border-radius: 18px;
  box-shadow: 0 8px 30px rgba(48,60,66,0.10);
}}

/* Streamlit bordered containers -> glass cards */
[data-testid="stVerticalBlockBorderWrapper"] {{
  background: rgba(255,255,255,0.55);
  -webkit-backdrop-filter: blur(16px) saturate(140%);
  backdrop-filter: blur(16px) saturate(140%);
  border: 1px solid rgba(255,255,255,0.65) !important;
  border-radius: 18px !important;
  box-shadow: 0 8px 26px rgba(48,60,66,0.09);
}}

/* ---- Brand header ------------------------------------------------------ */
.mf-header {{
  display:flex; align-items:center; justify-content:space-between;
  gap:16px; padding:18px 22px; margin-bottom:18px;
}}
.mf-brand {{ display:flex; align-items:center; gap:14px; }}
.mf-logo {{
  width:44px; height:44px; border-radius:12px; flex:0 0 auto;
  background: linear-gradient(135deg, {ORANGE}, #f4a25a);
  box-shadow: 0 6px 16px rgba(225,105,14,0.35);
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-weight:700; font-size:20px;
}}
.mf-title {{ font-size:22px; font-weight:700; color:var(--slate); line-height:1.1; }}
.mf-subtitle {{ font-size:13px; color:var(--muted); margin-top:2px; }}
.mf-user {{
  display:flex; align-items:center; gap:8px; padding:8px 14px;
  border-radius:999px; background:rgba(255,255,255,0.6);
  border:1px solid var(--border); color:var(--slate2); font-size:13px; font-weight:500;
}}
.mf-user .dot {{ width:8px; height:8px; border-radius:50%; background:{GREEN}; }}

/* ---- Stat tiles -------------------------------------------------------- */
.mf-stat {{ padding:16px 18px; }}
.mf-stat .label {{ font-size:12px; color:var(--muted); text-transform:uppercase;
  letter-spacing:0.06em; font-weight:600; }}
.mf-stat .value {{ font-size:30px; font-weight:700; color:var(--slate); line-height:1.1; margin-top:4px; }}
.mf-stat .accent {{ height:4px; border-radius:999px; margin-top:12px; }}

/* Distribution bar */
.mf-distbar {{ display:flex; height:12px; border-radius:999px; overflow:hidden;
  border:1px solid var(--border); }}
.mf-distbar > span {{ display:block; height:100%; }}
.mf-legend {{ display:flex; gap:16px; flex-wrap:wrap; margin-top:10px;
  font-size:12px; color:var(--slate2); }}
.mf-legend .k {{ display:inline-flex; align-items:center; gap:6px; }}
.mf-legend .sw {{ width:10px; height:10px; border-radius:3px; }}

/* ---- Badges ------------------------------------------------------------ */
.mf-badge {{
  display:inline-block; padding:2px 10px; border-radius:999px;
  font-size:11.5px; font-weight:600; line-height:1.5;
  border:1px solid transparent; white-space:nowrap;
}}
.mf-meta {{ color:var(--muted); font-size:12.5px; }}
.mf-ticket-title {{ font-weight:600; font-size:15px; color:var(--slate); }}

/* ---- Message bubbles --------------------------------------------------- */
.mf-msg {{
  background: rgba(255,255,255,0.7); border:1px solid var(--border);
  border-radius:14px; padding:12px 14px; margin-bottom:10px;
}}
.mf-msg .who {{ font-weight:600; font-size:13px; color:var(--slate); }}
.mf-msg .when {{ font-size:11.5px; color:var(--muted); }}
.mf-msg .body {{ font-size:14px; color:var(--slate2); margin-top:6px; white-space:pre-wrap; }}

/* ---- Buttons ----------------------------------------------------------- */
.stButton > button {{
  border-radius:12px; border:1px solid var(--border);
  background: rgba(255,255,255,0.7); color:var(--slate);
  font-weight:600; transition: all .15s ease;
}}
.stButton > button:hover {{
  border-color:{ORANGE}; color:{ORANGE};
  box-shadow:0 4px 14px rgba(225,105,14,0.18); transform:translateY(-1px);
}}
/* primary buttons = Milford orange */
.stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {{
  background: linear-gradient(135deg, {ORANGE}, #f0863a);
  color:#fff; border:none; box-shadow:0 6px 16px rgba(225,105,14,0.30);
}}
.stButton > button[kind="primary"]:hover {{ color:#fff; filter:brightness(1.04); }}

/* ---- Inputs ------------------------------------------------------------ */
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
[data-baseweb="select"] > div {{
  border-radius:10px !important;
}}
.stTextInput input:focus, .stTextArea textarea:focus {{
  border-color:{ORANGE} !important; box-shadow:0 0 0 2px rgba(225,105,14,0.15) !important;
}}

/* Empty-state panel */
.mf-empty {{ text-align:center; padding:40px 20px; color:var(--muted); }}
.mf-empty .big {{ font-size:15px; color:var(--slate2); font-weight:600; margin-bottom:4px; }}
</style>
"""
