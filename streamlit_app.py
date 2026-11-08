"""NyayaAI chat page.

Run from the project root:
    streamlit run streamlit_app.py

Design (owner's Stitch mock-ups, 2026-11-06): a glowing sphere on the start screen;
while NyayaAI works the sphere pulses; when the answer is ready it shrinks into the
small icon beside the answer, and the answer types itself out. For follow-up
questions the small sphere pulses instead. Every piece of text on the page must be
TRUE about what NyayaAI does (no invented numbers or features).
"""

import base64
import hmac
import html
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import uuid
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import openai
import streamlit as st
import streamlit.components.v1 as components

# On Streamlit Community Cloud, secrets are typed into the app's settings and appear in st.secrets.
# Copy them into environment variables BEFORE app.config reads them. A real environment variable
# or the local .env file still wins; locally there is no secrets file and nothing happens.
try:
    for _name in ("OPENAI_API_KEY", "APP_ACCESS_CODE", "OPENAI_MODEL", "ENABLED_DOMAINS"):
        if _name in st.secrets:
            os.environ.setdefault(_name, str(st.secrets[_name]))
except Exception:  # no secrets file
    pass

from app import config  # noqa: E402  (must come after the secrets are copied)
from app.conversation import question_with_context
from app.domains import load_domains
from app.services.answer_generator import DISCLAIMER as DISCLAIMER_TEXT
from app.services.answer_generator import ModelRefusedError
from app.filing_guides import guide_for, load_filing_guides
from app.services.document_explainer import DocumentUnreadable
from app.services.drafter import DRAFT_LABEL, DraftResult, is_consent
from app.services.voice import transcribe

ROOT = Path(__file__).parent
SOURCES = json.loads((ROOT / "data/legal_sources/sources.json").read_text(encoding="utf-8"))["sources"]
DOMAINS = load_domains(ROOT / "data/legal_sources/domains.json")
ENABLED_SOURCES = [s for s in SOURCES if s["domain"] in config.ENABLED_DOMAINS]
# "The Bharatiya Nyaya Sanhita, 2023" -> "Bharatiya Nyaya Sanhita 2023"
SHORT_NAME = {s["id"]: s["title"].removeprefix("The ").replace(",", "") for s in SOURCES}

SPHERE_ICON = str(ROOT / "assets/sphere_avatar.png")  # made by scripts/make_sphere_assets.py
SPHERE_BIG = base64.b64encode((ROOT / "assets/sphere_cut.png").read_bytes()).decode()
SPHERE_COMPONENT = (ROOT / "assets/sphere_component.html").read_text(encoding="utf-8")
LADY_ICON = base64.b64encode((ROOT / "assets/lady_justice_icon.png").read_bytes()).decode()

# Seconds between words when the answer "types" itself out. 0 = show at once (used by tests).
TYPEWRITER_DELAY = float(os.getenv("NYAYAAI_TYPEWRITER_DELAY", "0.025"))

st.set_page_config(page_title="NyayaAI", page_icon=SPHERE_ICON, layout="centered")

CONFIDENCE_LABELS = {
    "high": "Well supported by the text of the Acts",
    "medium": "Partly supported - some points need checking",
    "low": "Weakly supported - please check with a lawyer",
    "insufficient": "Not covered by the laws NyayaAI has",
}
THINKING_TEXT = f"Searching {len(ENABLED_SOURCES)} Acts and checking every quote…"
DOCUMENT_THINKING_TEXT = "Reading your document and checking every date, amount and quote…"
DOCUMENT_TYPES = ["pdf", "png", "jpg", "jpeg", "webp"]
MAX_UPLOAD_MB = 10
FILING_GUIDES = load_filing_guides(ROOT / "data/legal_sources/filing_guides.json")

# Drafting flow (only after the person agrees). The button texts are sent as the person's reply,
# so clicking and typing "yes" / "haan" work the same way.
DRAFT_THINKING_TEXT = "Preparing your draft from your own facts and the verified law…"
DRAFT_OFFER = "Would you like help preparing a letter or complaint about this?"
DRAFT_YES = "Yes, please help me draft it."
DRAFT_SKIP = "Please draft it now and leave blanks for anything I haven't said."
GUIDE_OFFER = "Would you like step-by-step guidance on sending or filing it?"
GUIDE_YES = "Yes, please guide me through the next steps."

# Internal citation IDs in the answer text, e.g. "[copyright_act_1957:13]" or "[patents_act_1970:117A]"
CITATION_ID = re.compile(r"\[([a-z_]+_\d{4}):(\w+)\]")

# ---------------------------------------------------------------------------
# Look and feel
# ---------------------------------------------------------------------------
STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Inter:wght@400;500;600&display=swap');

:root {
  --bg: #0b1020; --panel: #141a2b; --panel-2: #1a2236; --line: #252e45;
  --text: #e6e9f2; --muted: #8b93a7; --accent: #22d3ee; --accent-2: #a855f7;
}
html, body, .stApp { background: radial-gradient(1200px 600px at 50% -10%, #16203a 0%, var(--bg) 60%) fixed; }
.stApp, .stMarkdown, p, li, input, textarea, button { font-family: 'Inter', sans-serif; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { display: none; }  /* Streamlit's own (empty) header strip */

/* Top bar FIXED to the browser window (so it never scrolls away). No box: the page colour fades
   to transparent at its bottom, so answers scrolling underneath vanish softly. The side padding
   lines the bar up with the 820px-wide page content. */
.st-key-topbar {
  position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
  padding: .7rem max(1rem, calc((100vw - 820px) / 2 + 1rem)) 1.6rem;
  background: linear-gradient(to bottom, #0b1020 0%, #0b1020 78%, rgba(11, 16, 32, 0) 100%);
}
.block-container { padding-top: 7.5rem; }  /* room for the fixed top bar */
.logo { height: 44px; display: block; filter: drop-shadow(0 0 6px rgba(34, 211, 238, .35)); }

/* Keep Lady Justice / NyayaAI / i in ONE row on every screen. (On phones Streamlit stacks columns
   vertically, which made the pinned bar very tall and covered the page.) */
.st-key-topbar [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .6rem !important; }
.st-key-topbar [data-testid="stColumn"] { width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; }
.st-key-topbar [data-testid="stColumn"]:nth-child(3) { flex: 1 1 auto !important; }  /* NyayaAI fills the middle */
@media (max-width: 640px) {
  .st-key-topbar { padding: .5rem 1rem 1.2rem; }
  .logo { height: 34px; }
  [class*="st-key-brand"] button, [class*="st-key-brand"] button p { font-size: 1.6rem !important; }
  .tagline { font-size: .72rem; margin-top: -.2rem; }
  .block-container { padding-top: 7.2rem; }  /* the tagline wraps to 2 lines on phones */
}
.block-container { padding-bottom: 7rem; max-width: 820px; }

/* --- top bar: NyayaAI (click = new chat) + info button --- */
[class*="st-key-brand"] button {
  background: transparent !important; border: none !important; box-shadow: none !important;
  font-family: 'Cormorant Garamond', serif !important; font-size: 2rem !important;
  letter-spacing: 0.06em; color: var(--text) !important; padding: 0 !important;
}
[class*="st-key-brand"] button p { font-family: 'Cormorant Garamond', serif !important; font-size: 2rem !important; }
[class*="st-key-brand"] button:hover { color: var(--accent) !important; }
/* "i" button: a small round outlined circle at the right of the top bar */
[class*="st-key-info"] button {
  width: 2.1rem; height: 2.1rem; min-height: 0 !important; padding: 0 !important; border-radius: 50% !important;
  background: transparent !important; border: 1.5px solid var(--muted) !important; box-shadow: none !important;
  display: flex; align-items: center; justify-content: center;
}
[class*="st-key-info"] button:hover { border-color: var(--accent) !important; }
[class*="st-key-info"] button:hover p { color: var(--accent) !important; }
/* Remove the small "⌄" arrow Streamlit adds to popovers (hiding it alone still reserves space). */
[class*="st-key-info"] button span:has(> [data-testid="stIconMaterial"]) { display: none !important; }
[class*="st-key-info"] button p {
  font-family: 'Cormorant Garamond', serif !important; font-size: 1.3rem !important; font-weight: 700;
  font-style: normal; line-height: 1; color: var(--text) !important; margin: 0; text-align: center;
}
/* Centre the "i" exactly inside its circle (Streamlit wraps the label in several boxes) */
[class*="st-key-info"] button > div, [class*="st-key-info"] button [data-testid="stMarkdownContainer"] {
  width: 100%; display: flex; align-items: center; justify-content: center; margin: 0 !important;
}
.info-muted { color: var(--muted); font-size: .88em; }
/* three lines (history) button, left of the logo */
[class*="st-key-menu"] button { background: transparent !important; border: none !important; box-shadow: none !important;
                      padding: 0 .2rem !important; min-height: 0 !important; }
[class*="st-key-menu"] button p { font-size: 1.6rem !important; line-height: 1; color: var(--text) !important; }
[class*="st-key-menu"] button:hover p { color: var(--accent) !important; }
/* side panels (history on the left, information on the right) */
[role="dialog"] { background: var(--panel) !important; border-color: var(--line) !important; }
[role="dialog"] h4 { font-size: 1rem; margin: .9rem 0 .3rem; color: var(--accent); }
[role="dialog"] [data-testid="stHeaderActionElements"] { display: none; }
[role="dialog"] [class*="st-key-open_"] button { justify-content: flex-start !important; text-align: left !important; }
[role="dialog"] [class*="st-key-open_"] button > div { justify-content: flex-start !important; width: 100%; }
[role="dialog"] [class*="st-key-open_"] button p { text-align: left !important; overflow: hidden; text-overflow: ellipsis; }
.st-key-history_bridge { display: none; }
[data-testid="stPopoverBody"] h4 { font-size: 1rem; margin: .9rem 0 .3rem; color: var(--accent); }
[data-testid="stPopoverBody"] h4:first-child { margin-top: 0; }
[data-testid="stPopoverBody"] [data-testid="stHeaderActionElements"] { display: none; }  /* no link icon on headings */
iframe { border: none; }
/* Streamlit fades the page while it is working ("stale" elements). An answer takes 10-25 s, so on phones the
   whole screen looked like it was losing brightness (reported by a tester). Keep everything fully visible. */
[data-stale="true"], [data-stale="true"] * { opacity: 1 !important; transition: none !important; }
.st-key-topbar button:disabled { opacity: .45 !important; cursor: wait !important; }
.tagline { color: var(--muted); font-size: 0.82rem; margin: -0.4rem 0 1.2rem 0; letter-spacing: 0.02em; }

/* --- the sphere --- */
.hero { text-align: center; margin-top: 2.5rem; }
.sphere-wrap { display: flex; justify-content: center; }
.sphere {
  width: 300px; height: 300px; border-radius: 50%;
  filter: drop-shadow(0 0 40px rgba(34,211,238,0.35)) drop-shadow(0 0 90px rgba(168,85,247,0.25));
  animation: spin 40s linear infinite, breathe 6s ease-in-out infinite;
}
.sphere.thinking { animation: spin 6s linear infinite, pulse 1.2s ease-in-out infinite; }
.sphere.collapse { animation: collapse 0.7s cubic-bezier(.6,0,.4,1) forwards; }
.sphere.small { width: 46px; height: 46px; animation: spin 6s linear infinite, pulse-small 1.2s ease-in-out infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes breathe { 0%,100% { filter: drop-shadow(0 0 35px rgba(34,211,238,.30)) drop-shadow(0 0 80px rgba(168,85,247,.20)); }
                     50%     { filter: drop-shadow(0 0 55px rgba(34,211,238,.45)) drop-shadow(0 0 110px rgba(168,85,247,.30)); } }
@keyframes pulse { 0%,100% { scale: 1; filter: drop-shadow(0 0 40px rgba(34,211,238,.35)); }
                   50%     { scale: 1.08; filter: drop-shadow(0 0 80px rgba(34,211,238,.70)) drop-shadow(0 0 120px rgba(168,85,247,.45)); } }
@keyframes pulse-small { 0%,100% { scale: 1; } 50% { scale: 1.18; filter: drop-shadow(0 0 14px rgba(34,211,238,.8)); } }
@keyframes collapse { to { scale: 0.12; translate: -330px 140px; opacity: 0; } }
.hero h1 { font-family: 'Cormorant Garamond', serif; font-weight: 500; font-size: 2.9rem; color: var(--text); margin: 1.6rem 0 0.2rem 0; }
.hero p { color: var(--muted); font-size: 1.05rem; }
.status { display: inline-flex; align-items: center; gap: .5rem; margin-top: 1rem; padding: .35rem .9rem;
          border: 1px solid var(--line); border-radius: 999px; color: var(--text); font-size: .85rem; background: var(--panel); }
.status .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: .25; } }
.thinking-row { display: flex; align-items: center; gap: 1rem; margin: .6rem 0 .2rem .2rem; }
.status .secs { color: var(--muted); margin-left: .3rem; font-variant-numeric: tabular-nums; }

/* small Stop / Edit buttons */
.st-key-stop, .st-key-edit { display: flex; justify-content: center; }
.st-key-edit { justify-content: flex-end; }
.st-key-stop button, .st-key-edit button {
  background: transparent !important; border: 1px solid var(--line) !important; border-radius: 999px !important;
  color: var(--muted) !important; font-size: .78rem !important; padding: .1rem .9rem !important; min-height: 0 !important;
}
.st-key-stop button:hover { border-color: #f87171 !important; color: #fca5a5 !important; }
.st-key-edit button:hover { border-color: var(--accent) !important; color: var(--accent) !important; }

/* --- chat messages --- */
[data-testid="stChatMessage"] { background: transparent; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  flex-direction: row-reverse; text-align: left;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
  background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: .8rem 1.1rem; max-width: 85%;
}
[data-testid="stChatMessageAvatarCustom"] img { border-radius: 50%; filter: drop-shadow(0 0 8px rgba(34,211,238,.5)); }
/* User icon: Streamlit's own, restyled from a pink square to a thin outline in the theme colours */
[data-testid="stChatMessageAvatarUser"] { background: transparent !important; border: 1px solid var(--line);
                                          border-radius: 50%; color: var(--muted) !important; }
[data-testid="stChatMessageAvatarUser"] svg { color: var(--muted) !important; fill: currentColor; }
[data-testid="stChatMessage"] p { font-size: 1.02rem; line-height: 1.65; }

/* --- answer parts --- */
.pill { display: inline-block; padding: .25rem .75rem; border-radius: 999px; background: var(--panel-2);
        border: 1px solid var(--line); color: var(--muted); font-size: .8rem; margin: .2rem 0 .6rem 0; }
/* Confidence: a small coloured dot instead of an emoji */
.pill::before { content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%;
                margin-right: .5rem; vertical-align: middle; background: var(--muted); }
.pill.high::before { background: #34d399; }
.pill.medium::before { background: #fbbf24; }
.pill.low::before { background: #fb923c; }
.section-title { font-family: 'Cormorant Garamond', serif; font-size: 1.55rem; color: var(--text); margin: 1rem 0 .5rem 0; }
.section-title span { color: var(--accent); }
.step { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: .7rem 1rem;
        margin: .45rem 0; color: var(--text); }
.step::before { content: "•"; color: var(--accent); margin-right: .6rem; }
.unverified { color: #fbbf24; font-size: .85em; }
/* Quotes from an attached document: one panel, thin lines between rows (not a box per line) */
.qpanel { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: .2rem 1rem; margin: .4rem 0; }
.qrow { padding: .65rem 0; border-bottom: 1px solid var(--line); }
.qrow:last-child { border-bottom: none; }
.qquote { color: var(--accent); font-weight: 600; font-size: .95rem; }
.qmeaning { color: var(--text); font-size: .93rem; margin-top: .15rem; line-height: 1.5; }
.disclaimer { margin-top: 1rem; padding: .8rem 1rem; border-radius: 14px; background: var(--panel);
              border: 1px solid var(--line); color: var(--muted); font-size: .8rem; }
[data-testid="stExpander"] { border: 1px solid var(--line) !important; border-radius: 14px !important; background: var(--panel); }
[data-testid="stAlert"] { border-radius: 14px; }

/* --- example buttons and the question box --- */
.st-key-examples button { background: var(--panel) !important; border: 1px solid var(--line) !important;
                          border-radius: 999px !important; color: var(--text) !important; font-size: .85rem; }
.st-key-examples button:hover { border-color: var(--accent) !important; }
/* Rounded rectangle (not a full pill), so long multi-line questions stay inside the box */
[data-testid="stChatInput"] > div { border-radius: 22px !important; background: var(--panel) !important;
                                    border: 1px solid var(--line) !important; box-shadow: 0 0 30px rgba(34,211,238,.10);
                                    padding: 0.35rem 0.6rem 0.35rem 1rem !important; }
[data-testid="stChatInput"] textarea { padding-right: 0.5rem !important; }
</style>
"""


def sphere_html(css_class: str = "") -> str:
    """The sphere as a plain image (used for the small pulsing sphere on follow-up questions)."""
    return f'<img class="sphere {css_class}" src="data:image/png;base64,{SPHERE_BIG}" alt="">'


def show_sphere(mode: str, size: int = 300) -> None:
    """The big interactive sphere (WebGL, assets/sphere_component.html): "idle", "thinking" or "collapse"."""
    page = SPHERE_COMPONENT.replace("{{IMG}}", SPHERE_BIG).replace("{{MODE}}", mode).replace("{{SIZE}}", str(size))
    components.html(page, height=int(size * 1.7) + 10)  # canvas is 1.7x the sphere, to fit the glow


# ---------------------------------------------------------------------------
# Helpers (tested in tests/test_streamlit_app.py)
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner="Loading the law and search models (about 20 seconds, first time only)...")
def load_assistant():
    """Build the pipeline once and reuse it for every visitor and every message."""
    from scripts.search import build_assistant

    return build_assistant()


@st.cache_resource(show_spinner="Preparing the document reader...")
def load_explainer():
    """'Explain my document', sharing the chat pipeline's search and OpenAI client."""
    from scripts.search import build_document_explainer

    assistant = load_assistant()
    return build_document_explainer(retriever=assistant.retriever, client=assistant.client)


@st.cache_resource(show_spinner="Preparing the drafting assistant...")
def load_drafter():
    """Letter/complaint drafting, sharing the chat pipeline's OpenAI client."""
    from scripts.search import build_drafter

    return build_drafter(client=load_assistant().client)


def readable_citations(text: str) -> str:
    """Turn internal IDs like "[copyright_act_1957:13]" into "(Section 13, Copyright Act 1957)" for people."""
    def replace(match: re.Match) -> str:
        act = SHORT_NAME.get(match.group(1), match.group(1))  # "Copyright Act 1957"
        return f"(Section {match.group(2)}, {act})"

    return CITATION_ID.sub(replace, text)


def typewriter(text: str):
    """Yield the answer word by word, for st.write_stream."""
    for word in re.split(r"(\s+)", text):
        yield word
        if word.strip():
            time.sleep(TYPEWRITER_DELAY)


def show_answer(response, animate: bool = False) -> None:
    """Display one NyayaAI answer: text, confidence, safety notes, next steps, sources, disclaimer."""
    notes = getattr(response, "safety_notes", [])
    for note in notes:
        if note.kind == "old_law":
            st.warning(f"**Date check:** {note.text}  \n*Source: {note.source}*")
        elif note.kind == "state_law":
            st.warning(f"**Your State's law:** {note.text}")

    answer = readable_citations(response.answer)
    if animate and TYPEWRITER_DELAY > 0:
        st.write_stream(typewriter(answer))
    else:
        st.markdown(answer)
    st.markdown(f'<span class="pill {html.escape(response.confidence)}">{CONFIDENCE_LABELS.get(response.confidence, response.confidence)}</span>',
                unsafe_allow_html=True)

    helplines = [n for n in notes if n.kind == "helpline"]
    if helplines:
        st.info("**Get help now**  \n" + "  \n".join(f"{n.text} *(source: {n.source})*" for n in helplines))

    if response.next_steps:
        steps = "".join(f'<div class="step">{html.escape(readable_citations(step))}</div>'
                        for step in response.next_steps)
        st.markdown(f'<div class="section-title">What you can do next</div>{steps}',
                    unsafe_allow_html=True)

    show_sources(response.citations)
    st.markdown(f'<div class="disclaimer">{html.escape(response.disclaimer)}</div>', unsafe_allow_html=True)


def show_sources(citations) -> None:
    """The 'Sources' box: every quote from the Acts, verified (or not) by code."""
    if not citations:
        return
    verified = sum(c.verified for c in citations)
    with st.expander(f"Sources: {verified} of {len(citations)} citations verified in the official text"):
        for c in citations:
            where = f"{c.citation}, page {c.page} of the India Code PDF" if c.citation else c.section_id
            if c.verified:
                st.markdown(f"**Verified:** {where}  \n> {c.quote}  \n*Supports:* {readable_citations(c.supports)}")
            else:
                st.markdown(f"**Could not verify** ({where}): {c.reason}  \n"
                            f"*Claim:* {readable_citations(c.supports)}")


QUOTES_SHOWN_FIRST = 6  # longer lists: the rest is behind "Show more"


def quote_rows(items) -> str:
    """Quotes from the user's document with their meaning, as rows of ONE panel. Unverified ones are marked."""
    rows = []
    for q in items:
        mark = "" if q.verified else ' <span class="unverified">(these exact words were not found in your document)</span>'
        rows.append(f'<div class="qrow"><div class="qquote">&ldquo;{html.escape(q.quote)}&rdquo;{mark}</div>'
                    f'<div class="qmeaning">{html.escape(q.meaning)}</div></div>')
    return f'<div class="qpanel">{"".join(rows)}</div>'


def show_quotes(title: str, items) -> None:
    st.markdown(f'<div class="section-title">{title}</div>' + quote_rows(items[:QUOTES_SHOWN_FIRST]),
                unsafe_allow_html=True)
    if len(items) > QUOTES_SHOWN_FIRST:
        with st.expander(f"Show {len(items) - QUOTES_SHOWN_FIRST} more"):
            st.markdown(quote_rows(items[QUOTES_SHOWN_FIRST:]), unsafe_allow_html=True)


def law_line(m) -> str:
    if m.section_id:
        return f"{m.as_written}: NyayaAI has this section; what it says is explained below."
    if m.covered:
        return f"{m.as_written}: NyayaAI has this Act."
    if m.source_id:
        return f"{m.as_written}: NyayaAI has this Act, but no section with this number. Please check the number."
    return f"{m.as_written}: NyayaAI does not have this law, so it cannot explain it. Please ask a lawyer about it."


def show_document_answer(response, animate: bool = False) -> None:
    """Display an explained document: summary, dates/amounts, key points, laws, next steps, checks."""
    if response.from_photo:
        st.warning("**Read from a photo.** Reading mistakes are possible: check names, dates and amounts "
                   "against your paper. (Quotes below were checked against the text read from the photo.)")
    if response.truncated:
        st.warning("Your document is long; only its first part was read and explained.")
    if response.unverified_figures:
        listed = ", ".join(f'"{f.text}"' for f in response.unverified_figures)
        st.warning(f"**Check this:** NyayaAI wrote {listed}, but could not find it in your document or in the "
                   "law it used. Do not rely on it.")

    st.markdown(f'<div class="section-title">{html.escape(response.document_type)}</div>', unsafe_allow_html=True)
    summary = readable_citations(response.summary)
    if animate and TYPEWRITER_DELAY > 0:
        st.write_stream(typewriter(summary))
    else:
        st.markdown(summary)
    st.markdown(f'<span class="pill {html.escape(response.confidence)}">'
                f'{CONFIDENCE_LABELS.get(response.confidence, response.confidence)}</span>', unsafe_allow_html=True)

    if response.deadlines_and_amounts:
        show_quotes("Dates, deadlines and amounts", response.deadlines_and_amounts)
    if response.key_points:
        show_quotes("What it says", response.key_points)
    if response.laws:
        st.markdown('<div class="section-title">Laws your document mentions</div>'
                    + "".join(f'<div class="step">{html.escape(law_line(m))}</div>' for m in response.laws),
                    unsafe_allow_html=True)
    if response.law_explanation.strip():
        st.markdown('<div class="section-title">What the law says</div>', unsafe_allow_html=True)
        st.markdown(readable_citations(response.law_explanation))
    if response.next_steps:
        steps = "".join(f'<div class="step">{html.escape(readable_citations(s))}</div>' for s in response.next_steps)
        st.markdown(f'<div class="section-title">What you can do next</div>{steps}', unsafe_allow_html=True)

    show_sources(response.citations)
    with st.expander("What NyayaAI read from your document"):
        st.text(response.document_text)
    st.markdown(f'<div class="disclaimer">{html.escape(response.disclaimer)}</div>', unsafe_allow_html=True)


def show_draft_questions(response, animate: bool = False) -> None:
    """NyayaAI's questions before drafting (only facts that change the letter; never names or addresses)."""
    intro = f"To prepare a **{response.label.lower()}**, I need a few details:"
    st.markdown(intro)
    st.markdown("\n".join(f"{i}. {q}" for i, q in enumerate(response.plan.questions, start=1)))
    st.caption("Answer in one message, in your own words. Please leave out names, addresses and phone numbers: "
               "the draft keeps blanks for those, and you fill them in yourself.")


def show_draft(response, key: str) -> None:
    """A checked draft: label, warnings from the code checks, editable text, download, verified law."""
    st.markdown(f'<div class="section-title">{html.escape(response.label)}</div>', unsafe_allow_html=True)
    st.info(DRAFT_LABEL)
    if response.unverified_figures:
        listed = ", ".join(f'"{f.text}"' for f in response.unverified_figures)
        st.warning(f"**Check this:** the draft contains {listed}, which you did not write. Change or remove it.")
    if response.law_in_body:
        listed = ", ".join(f'"{t}"' for t in response.law_in_body)
        st.warning(f"**Check this:** the letter mentions {listed} in its text, which NyayaAI could not check. "
                   "Remove it, or ask a lawyer.")
    if response.removed_law:
        st.caption(f"{len(response.removed_law)} legal reference(s) could not be verified in the official text "
                   "and were left out of the draft.")

    edited = st.text_area("Your draft (you can edit it here)", value=response.full_text(), height=440, key=key)
    st.download_button("Download draft", data=edited, file_name=f"NyayaAI_DRAFT_{response.document_type}.txt",
                       mime="text/plain", key=f"{key}_download")
    if response.blanks:
        st.caption("Blanks to fill in: " + ", ".join(response.blanks))
    st.caption("Your edits are not sent to OpenAI and are not saved by NyayaAI; download the draft to keep it.")
    if response.check_before_sending:
        steps = "".join(f'<div class="step">{html.escape(s)}</div>' for s in response.check_before_sending)
        st.markdown(f'<div class="section-title">Check before you use it</div>{steps}', unsafe_allow_html=True)
    show_sources(response.law)
    st.markdown(f'<div class="disclaimer">{html.escape(DISCLAIMER_TEXT)}</div>', unsafe_allow_html=True)


def law_citation(section_id_: str) -> str:
    source_id, number = section_id_.split(":")
    return f"Section {number}, {SHORT_NAME.get(source_id, source_id)}"


def show_guide(response, animate: bool = False) -> None:
    """The filing guide: fixed, hand-checked text from filing_guides.json (never written by the model)."""
    guide = guide_for(FILING_GUIDES, response.guide)
    if guide:
        st.markdown(f'<div class="section-title">{html.escape(guide["title"])}</div>', unsafe_allow_html=True)
        for step in guide["steps"]:
            lines = [f"**{step['heading']}**", step["text"]]
            if step.get("link"):
                lines.append(f"Official site: {step['link']}")
            if step.get("law"):
                lines.append(f"*{law_citation(step['law']['section_id'])}:* \"{step['law']['quote']}\"")
            st.markdown("  \n".join(lines))
        keep = "".join(f'<div class="step">{html.escape(d)}</div>' for d in guide["documents_to_keep"])
        st.markdown(f'<div class="section-title">Useful to keep</div>{keep}', unsafe_allow_html=True)
        st.caption("These help prove your case; they are suggestions, not a list required by law.")
        st.markdown(f"**Proof that you sent or filed it:** {guide['acknowledgement']}")
    else:
        st.markdown("NyayaAI does not have a checked filing guide for this kind of document yet. "
                    "A lawyer or the free legal aid service below can tell you where to send it.")
    st.info(FILING_GUIDES["legal_aid"]["text"])
    st.caption(f"Links and steps checked on official government websites on {FILING_GUIDES['checked_on']}. "
               "NyayaAI only guides you: it does not send, file or track anything for you.")


def show_any_answer(response, animate: bool = False, key: str = "draft") -> None:
    kind = getattr(response, "kind", "")
    if kind == "document":
        show_document_answer(response, animate)
    elif kind == "draft_questions":
        show_draft_questions(response, animate)
    elif kind == "draft":
        show_draft(response, key)
    elif kind == "guide":
        show_guide(response, animate)
    else:
        show_answer(response, animate)


def offers_draft(response) -> bool:
    """Offer a draft only after a real answer: not out of scope, and at least one verified quote."""
    return (getattr(response, "kind", "") == "" and response.confidence != "insufficient"
            and any(c.verified for c in response.citations))


def not_now() -> None:
    st.session_state.flow = None


def ask_from_button(text: str) -> None:
    st.session_state.pending_question = text


def show_offer(flow: dict | None) -> None:
    """The follow-up offer under NyayaAI's latest message (nothing happens until the person agrees)."""
    if not flow:
        return
    if flow["stage"] == "offered":
        st.markdown(f"**{DRAFT_OFFER}**")
        st.button("Yes, help me draft it", key="draft_yes", on_click=ask_from_button, args=(DRAFT_YES,))
        st.caption("Or type your reply: you can add more details, or ask something else.")
    elif flow["stage"] == "asking":
        draft_col, later_col, _ = st.columns([2, 1, 2])
        draft_col.button("Draft it with blanks", key="draft_skip", on_click=ask_from_button, args=(DRAFT_SKIP,))
        later_col.button("Not now", key="draft_cancel", on_click=not_now)
    elif flow["stage"] == "guide_offered":
        st.markdown(f"**{GUIDE_OFFER}**")
        st.button("Yes, guide me", key="guide_yes", on_click=ask_from_button, args=(GUIDE_YES,))


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.markdown(STYLE, unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_id" not in st.session_state:
    st.session_state.chat_id = uuid.uuid4().hex
    st.session_state.history = []  # past chats, kept ONLY in this browser (localStorage), see sync_history()
    st.session_state.history_loaded = False


# ---------------------------------------------------------------------------
# Chat history, saved only in the user's own browser (localStorage). Nothing is stored on the server.
# A tiny JavaScript bridge reads the saved chats once when the page opens and writes them back after each answer.
# ---------------------------------------------------------------------------
HISTORY_MAX_CHATS = 30
HISTORY_JS = """
export default function(component) {
  const { data, setStateValue } = component;
  const KEY = "nyayaai_history_v1";
  if (!data || !data.loaded) {
    let saved = "[]";
    try { saved = window.localStorage.getItem(KEY) || "[]"; } catch (e) { saved = "[]"; }
    setStateValue("saved", saved);
    return;
  }
  try {
    if (window.localStorage.getItem(KEY) !== data.history) { window.localStorage.setItem(KEY, data.history); }
  } catch (e) {}
}
"""
history_bridge = st.components.v2.component("nyayaai_history", js=HISTORY_JS)


def load_history() -> None:
    """Called once, when the browser has sent its saved chats."""
    state = st.session_state.get("history_bridge") or {}
    try:
        chats = json.loads(state.get("saved") or "[]")
    except (TypeError, ValueError, AttributeError):
        chats = []
    if not isinstance(chats, list):
        chats = []
    valid = [c for c in chats if isinstance(c, dict) and c.get("id") and isinstance(c.get("messages"), list)]
    current = [c for c in st.session_state.history if c["id"] not in {v["id"] for v in valid}]
    st.session_state.history = (current + valid)[:HISTORY_MAX_CHATS]
    st.session_state.history_loaded = True


def sync_history() -> None:
    """Mount the bridge (end of every run): first read the browser's chats, afterwards write them back."""
    loaded = st.session_state.history_loaded
    data = {"loaded": loaded,
            "history": json.dumps(st.session_state.history, ensure_ascii=False) if loaded else None}
    history_bridge(data=data, key="history_bridge", on_saved_change=load_history)


def local_time() -> str:
    try:
        return datetime.now(ZoneInfo(st.context.timezone)).strftime("%d %b %Y, %H:%M")
    except Exception:
        return datetime.now().strftime("%d %b %Y, %H:%M")


def start_new_chat() -> None:
    st.session_state.messages = []
    st.session_state.flow = None
    st.session_state.editing = False
    st.session_state.chat_id = uuid.uuid4().hex


def open_chat(chat_id: str) -> None:
    chat = next((c for c in st.session_state.history if c["id"] == chat_id), None)
    if chat:
        start_new_chat()
        st.session_state.messages = [dict(m) for m in chat["messages"]]
        st.session_state.chat_id = chat_id


def delete_chat(chat_id: str) -> None:
    st.session_state.history = [c for c in st.session_state.history if c["id"] != chat_id]
    if st.session_state.chat_id == chat_id:
        start_new_chat()


def delete_all_history() -> None:
    st.session_state.history = []
    start_new_chat()

def show_info() -> None:
    """Contents of the "i" (information) panel in the top bar."""
    st.markdown("Plain-language legal information for India, answered **only** from the official text of the "
                "Acts (India Code). Every quote is checked word for word before you see it.")

    st.markdown("#### How to ask")
    st.markdown("- **Type** in English, Hindi or Hinglish\n"
                "- **Speak** with the microphone (you check the words before sending)\n"
                "- **Attach** a notice or letter (PDF or photo) to have it explained")

    st.markdown("#### What it covers")
    for domain in config.ENABLED_DOMAINS:
        acts = [s for s in ENABLED_SOURCES if s["domain"] == domain]
        info = DOMAINS[domain]
        covers = info["covers"] + (f", {info['display_also']}" if info.get("display_also") else "")
        label = info["label"][0].upper() + info["label"][1:]
        st.markdown(f"**{label}** ({len(acts)} {'Act' if len(acts) == 1 else 'Acts'})  \n"
                    f"<span class='info-muted'>{covers}</span>", unsafe_allow_html=True)
    with st.expander(f"All {len(ENABLED_SOURCES)} Acts and their dates"):
        st.markdown("\n".join(
            f"- {s['title']} " + (f"(as on {s['version_as_on']})" if s.get("version_as_on")
                                  else "(consolidated text; India Code prints no 'as on' date)")
            for s in ENABLED_SOURCES))

    st.markdown("#### Not covered yet")
    st.markdown("Rules, fees, court judgments, State laws (except Delhi's rent law), inheritance, land records, "
                "stamp duty, and other areas (family, employment, tax...). For these NyayaAI says so instead of guessing.")

    st.markdown("#### Privacy")
    st.markdown("Questions, documents and recordings are sent to OpenAI to write the answer; NyayaAI's server "
                "does not store them. Your chat history is saved only in this browser (History, top right), "
                "and you can delete it at any time. Please leave out names, phone numbers and addresses; "
                "cover them on documents if you can.")

    st.caption("Legal information, not legal advice. For decisions, consult a qualified lawyer.")


@st.dialog("Your past chats", position="left", width="small")
def history_panel() -> None:
    show_history()


@st.dialog("About NyayaAI", position="right", width="small")
def info_panel() -> None:
    show_info()


def show_history() -> None:
    """Contents of the History panel: past chats saved in this browser, with Open and Delete."""
    st.caption("Saved only in this browser on this device: not on NyayaAI's server and not visible to anyone else. "
               "Anyone using this browser can see them, so delete them on a shared computer.")
    if not st.session_state.history_loaded:
        st.caption("Loading...")
        return
    if not st.session_state.history:
        st.caption("No saved chats yet. Your chats appear here after NyayaAI answers.")
        return
    for chat in st.session_state.history:
        open_col, delete_col = st.columns([5, 1.6], vertical_alignment="center")
        current = " (open now)" if chat["id"] == st.session_state.chat_id else ""
        if open_col.button(f"{chat['title']}{current}", key=f"open_{chat['id']}",
                           help=f"Last message: {chat.get('updated', '')}", use_container_width=True):
            open_chat(chat["id"])
            st.rerun()  # closes the panel and shows the chat
        if delete_col.button("Delete", key=f"delete_{chat['id']}"):
            delete_chat(chat["id"])
            st.rerun()  # full rerun, so the browser's copy is updated too
    if st.button("Delete all history", key="delete_all_history"):
        delete_all_history()
        st.rerun()


def response_to_text(r) -> str:
    """A plain copy of one NyayaAI reply, for the browser history (re-shown read-only when a chat is reopened)."""
    kind = getattr(r, "kind", "")
    if kind == "document":
        parts = [f"**{r.document_type}**", readable_citations(r.summary)]
        parts += [f'- "{q.quote}": {q.meaning}' for q in r.deadlines_and_amounts + r.key_points]
        steps = r.next_steps
    elif kind == "draft_questions":
        parts = [f"To prepare a **{r.label.lower()}**, I need a few details:"]
        parts += [f"{i}. {q}" for i, q in enumerate(r.plan.questions, start=1)]
        steps = []
    elif kind == "draft":
        parts = [f"**{r.label}** (DRAFT: review and complete it before use)", "```\n" + r.full_text() + "\n```"]
        steps = []
    elif kind == "guide":
        guide = guide_for(FILING_GUIDES, r.guide)
        parts = [f"**{guide['title']}**"] if guide else []
        for s in (guide["steps"] if guide else []):
            parts.append(f"- **{s['heading']}** {s['text']}" + (f" Official site: {s['link']}" if s.get("link") else ""))
        parts.append(FILING_GUIDES["legal_aid"]["text"])
        steps = []
    else:
        parts = [readable_citations(r.answer), f"*{CONFIDENCE_LABELS.get(r.confidence, r.confidence)}*"]
        parts += [f"> {n.text}" for n in getattr(r, "safety_notes", [])]
        steps = r.next_steps
    if steps:
        parts += ["**What you can do next**"] + [f"- {readable_citations(s)}" for s in steps]
    verified = [c for c in (getattr(r, "citations", None) or getattr(r, "law", None) or []) if c.verified]
    if verified:
        parts += ["**Sources (verified in the official text)**"] + [f'- {c.citation}: "{c.quote}"' for c in verified]
    return "\n\n".join(parts)


def saved_message(m: dict) -> dict | None:
    if m["role"] == "assistant":
        return {"role": "assistant_text", "text": response_to_text(m["response"])}
    if m["role"] in ("assistant_text", "stopped"):
        return dict(m)
    return {k: m[k] for k in ("role", "content", "flow", "attachment", "context") if k in m}


def save_current_chat() -> None:
    """Put the current conversation at the top of the history (written to the browser at the end of the run)."""
    msgs = [s for s in (saved_message(m) for m in st.session_state.messages) if s]
    if not msgs:
        return
    title = next((m["content"] for m in msgs if m["role"] == "user"), "Conversation")
    chat = {"id": st.session_state.chat_id, "title": title[:70] + ("..." if len(title) > 70 else ""),
            "updated": local_time(), "messages": msgs}
    others = [c for c in st.session_state.history if c["id"] != chat["id"]]
    st.session_state.history = [chat] + others[:HISTORY_MAX_CHATS - 1]


# Top bar: logo, NyayaAI (click = new chat) and an "i" button on the right that opens the information panel.
# Wrapped in a container that CSS pins to the top of the window (stays visible when scrolling).
with st.container(key="topbar"):
    topbar_slot = st.empty()  # filled by draw_topbar() once we know whether an answer is being prepared


def draw_topbar(busy: bool) -> None:
    """Three lines (chat history), logo, NyayaAI (new chat) and i (information).

    While NyayaAI is preparing an answer the buttons are greyed out: any click restarts the page, which would
    abandon the answer (only the Stop button should do that). Busy and normal versions use different keys, so the
    bar can be drawn twice in one run (busy first, then normal again when the answer is shown).
    """
    suffix = "_busy" if busy else ""
    wait = "Available when the answer is ready" if busy else None
    with topbar_slot.container():
        menu_col, logo_col, brand_col, info_col = st.columns([0.6, 0.6, 9.6, 0.9], vertical_alignment="center")
        with menu_col:
            if st.button("\u2630", key=f"menu{suffix}", disabled=busy,
                         help=wait or "Your past chats (saved only in this browser)"):
                history_panel()
        with logo_col:
            st.markdown(f'<img class="logo" src="data:image/png;base64,{LADY_ICON}" alt="Lady Justice">',
                        unsafe_allow_html=True)
        with brand_col:
            if st.button("NyayaAI", key=f"brand{suffix}", disabled=busy, help=wait or "Start a new conversation"):
                start_new_chat()
                st.rerun()
        with info_col:
            if st.button("i", key=f"info{suffix}", disabled=busy,
                         help=wait or "About NyayaAI: what it covers, how to ask, privacy"):
                info_panel()
        st.markdown('<div class="tagline">Legal information, not legal advice. For decisions, consult a qualified '
                    'lawyer.</div>', unsafe_allow_html=True)


if not config.OPENAI_API_KEY:
    draw_topbar(busy=False)
    st.error("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key, then restart.")
    st.stop()

# Optional access code for the public demo (set APP_ACCESS_CODE as a secret on the host):
# the page is public, but every question is paid from the owner's OpenAI account.
if config.APP_ACCESS_CODE and not st.session_state.get("access_ok"):
    draw_topbar(busy=False)
    code = st.text_input("This demo needs an access code", type="password", key="access_code")
    if code and hmac.compare_digest(code.strip(), config.APP_ACCESS_CODE):
        st.session_state.access_ok = True
        st.rerun()
    if code:
        st.error("That access code is not correct.")
    st.stop()

# A question that was still being answered when the page reloaded (the Stop button, or a new
# question sent meanwhile) stays in the chat, marked as stopped.
if st.session_state.get("in_progress"):
    st.session_state.messages.append({"role": "user", "content": st.session_state.pop("in_progress")})
    st.session_state.messages.append({"role": "stopped"})


def start_editing() -> None:
    st.session_state.editing = True


# The question box (Streamlit pins it to the bottom of the page wherever it is created).
# It also takes one file (a PDF or photo of a notice) and a voice recording.
raw = st.chat_input("Describe your problem, or attach a notice to explain", accept_file=True,
                    file_type=DOCUMENT_TYPES, accept_audio=True, max_upload_size=MAX_UPLOAD_MB)
typed, upload, recording = "", None, None
if isinstance(raw, str):
    typed = raw
elif raw is not None:
    typed = (raw.text or "").strip()
    upload = raw.files[0] if raw.get("files") else None
    recording = raw.get("audio")

# Voice: turn the recording into text, then let the person CHECK it before it is sent.
if recording is not None and not typed and upload is None:
    try:
        heard = transcribe(recording.getvalue(), recording.name, load_assistant().client, config.TRANSCRIBE_MODEL)
    except openai.APIError:
        heard = None
        st.error("Sorry, the voice service could not be reached. Please type your question instead.")
    if heard:
        st.session_state.heard = st.session_state.heard_box = heard
    elif heard == "":
        st.warning("NyayaAI could not hear any words. Please try again, or type your question.")

document = None
if upload is not None:
    document = {"name": upload.name, "type": upload.type, "data": upload.getvalue(), "note": typed}
question = typed or st.session_state.pop("pending_question", None)
if document and not question:
    question = "Please explain this document."
if question:
    st.session_state.editing = False
    st.session_state.pop("heard", None)
draw_topbar(busy=bool(question))

# What this message does. Drafting happens ONLY after the person agreed (button or a typed "yes"/"haan");
# anything else is answered as a normal question and the offer is dropped.
flow = st.session_state.get("flow")
action = "ask"
if document:
    action = "document"
elif question and flow:
    if flow["stage"] == "offered" and is_consent(question):
        action = "plan"
    elif flow["stage"] == "asking":
        action = "write"  # the reply to NyayaAI's questions (or "draft it with blanks")
    elif flow["stage"] == "guide_offered" and is_consent(question):
        action = "guide"

# Earlier messages of this conversation (no animation when shown again).
messages = st.session_state.messages
last_user = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=None)
for index, message in enumerate(messages):
    if message["role"] == "assistant":
        with st.chat_message("assistant", avatar=SPHERE_ICON):
            show_any_answer(message["response"], key=f"draft_{index}")
            if index == len(messages) - 1 and not question:
                show_offer(flow)
    elif message["role"] == "assistant_text":  # a reply from a chat reopened from the browser history
        with st.chat_message("assistant", avatar=SPHERE_ICON):
            st.markdown(message["text"])
            st.caption("Saved copy from this browser's history.")
    elif message["role"] == "stopped":
        with st.chat_message("assistant", avatar=SPHERE_ICON):
            st.caption("Stopped. No answer was given to this question.")
    else:
        with st.chat_message("user"):
            if index == last_user and st.session_state.get("editing"):
                # Edit the latest question, then send it again (its old answer is replaced).
                edited = st.text_area("Edit your question", value=message["content"], key="edit_box",
                                      label_visibility="collapsed")
                resend_col, cancel_col, _ = st.columns([1, 1, 4])
                if resend_col.button("Resend", key="resend", type="primary") and edited.strip():
                    del messages[index:]
                    st.session_state.editing = False
                    st.session_state.flow = None
                    st.session_state.pending_question = edited.strip()
                    st.rerun()
                if cancel_col.button("Cancel", key="cancel_edit"):
                    st.session_state.editing = False
                    st.rerun()
            else:
                st.markdown(message["content"])
                if message.get("attachment"):
                    st.caption(f"Attached: {message['attachment']}")
                elif index == last_user and not question and not message.get("flow"):  # new question: own Edit button
                    st.button("Edit", key="edit", on_click=start_editing)

# What NyayaAI heard from a voice recording: checked (and corrected) by the person before sending.
if st.session_state.get("heard") and not question:
    with st.container(key="heard_panel"):
        st.caption("NyayaAI heard this. Please check it and correct any mistakes, then send.")
        checked = st.text_area("What NyayaAI heard", key="heard_box", label_visibility="collapsed")
        send_col, cancel_col, _ = st.columns([1, 1, 4])
        if send_col.button("Send", key="send_heard", type="primary") and checked.strip():
            st.session_state.pop("heard", None)
            st.session_state.pending_question = checked.strip()
            st.rerun()
        if cancel_col.button("Cancel", key="cancel_heard"):
            st.session_state.pop("heard", None)
            st.rerun()

first_question = not st.session_state.messages

# Start screen: only the big interactive sphere (owner's choice: no headline, no example buttons).
if first_question and not question and not st.session_state.get("heard"):
    with st.container(key="start_screen"):
        show_sphere("idle", size=380)


@st.cache_resource
def background_workers() -> ThreadPoolExecutor:
    """Threads that run the (slow) answering, so the page can still react to the Stop button."""
    return ThreadPoolExecutor(max_workers=4)


def plan_then_maybe_write(drafter, flow: dict, consent: str):
    """Ask for missing facts; if nothing is missing, write the draft straight away."""
    questions = drafter.plan(flow["problem"], flow["answer"], consent)
    if questions.plan.questions:
        return questions
    return drafter.write(flow["problem"], flow["answer"], questions.plan, consent)


def status_pill(seconds: int, text: str = THINKING_TEXT) -> str:
    return (f'<div class="hero"><div class="status"><span class="dot"></span>{text}'
            f'<span class="secs">{seconds}s</span></div></div>')


if question:
    # Thinking: on the first question the big sphere pulses ABOVE the question; on follow-ups the same big
    # sphere pulses in the middle BELOW the new question (earlier messages stay above, to scroll back and read).
    # Both show a Stop button.
    thinking = st.empty()
    if first_question:
        with thinking.container():
            show_sphere("thinking", size=340)
            status = st.empty()
            st.button("Stop", key="stop")  # clicking reloads the page; the answer below is abandoned

    with st.chat_message("user"):
        st.markdown(question)
        if document:
            st.caption(f"Attached: {document['name']}")
        edit_slot = st.empty()  # gets this question's Edit button once the answer is shown

    if not first_question:
        thinking = st.empty()
        with thinking.container():
            show_sphere("thinking", size=280)
            status = st.empty()
            st.button("Stop", key="stop")

    # Remember the question until its answer is shown: if the page reloads first, it is marked "stopped".
    st.session_state.in_progress = question
    try:
        thinking_text = DRAFT_THINKING_TEXT
        if action == "document":
            explainer = load_explainer()
            job = background_workers().submit(explainer.explain_file, document["data"], document["type"],
                                              document["name"], document["note"])
            thinking_text = DOCUMENT_THINKING_TEXT
        elif action == "plan":
            job = background_workers().submit(plan_then_maybe_write, load_drafter(), flow, question)
        elif action == "write":
            facts = "" if question == DRAFT_SKIP else question
            job = background_workers().submit(load_drafter().write, flow["problem"], flow["answer"],
                                              flow["plan"].plan, flow["consent"], facts)
        elif action == "guide":  # fixed, checked text: no AI call
            job = background_workers().submit(SimpleNamespace, kind="guide", guide=flow["guide"])
        else:
            assistant = load_assistant()
            asked = question_with_context(messages, question)
            job = background_workers().submit(assistant.ask, asked)
            thinking_text = THINKING_TEXT
        started = time.monotonic()
        while not job.done():
            # Updating the page here also lets Streamlit notice a Stop click and end this run.
            status.markdown(status_pill(int(time.monotonic() - started), thinking_text), unsafe_allow_html=True)
            time.sleep(0.5)
        response = job.result()
    except DocumentUnreadable as problem:
        st.session_state.pop("in_progress", None)
        thinking.empty()
        st.warning(str(problem))
        draw_topbar(busy=False)
        st.stop()
    except (openai.APIError, ModelRefusedError):
        st.session_state.pop("in_progress", None)
        thinking.empty()
        st.error("Sorry, the AI service could not answer right now. Please try again in a moment.")
        draw_topbar(busy=False)
        st.stop()
    except Exception:  # e.g. a damaged PDF; the full error goes to the server log, not the page
        logging.getLogger("nyayaai").exception("Could not complete the request (%s)", action)
        st.session_state.pop("in_progress", None)
        thinking.empty()
        if action == "document":
            st.error("Sorry, NyayaAI could not read this file. Please try a PDF or a clear photo of the page.")
        else:
            st.error("Sorry, something went wrong. Please try again in a moment.")
        draw_topbar(busy=False)
        st.stop()
    st.session_state.pop("in_progress", None)

    # Answer ready: the big sphere shrinks away and reappears as the small icon beside the answer.
    if TYPEWRITER_DELAY > 0:
        with thinking.container():
            show_sphere("collapse", size=340 if first_question else 280)
        time.sleep(0.8)
    thinking.empty()

    # Where the drafting flow goes next (None = no offer).
    if action == "ask":
        flow = {"stage": "offered", "problem": asked, "answer": response} if offers_draft(response) else None
    elif action == "plan" and response.kind == "draft_questions":
        flow = {**flow, "stage": "asking", "consent": question, "plan": response}
    elif action in ("plan", "write"):
        flow = {"stage": "guide_offered", "guide": response.guide}
    else:
        flow = None
    st.session_state.flow = flow

    with st.chat_message("assistant", avatar=SPHERE_ICON):
        show_any_answer(response, animate=True, key=f"draft_{len(messages) + 1}")
        show_offer(flow)

    if action == "document":
        # Follow-up questions ("what should I reply?") get a short description of the document as context.
        messages.append({"role": "user", "content": question, "attachment": document["name"],
                         "context": f"I attached a document ({response.document_type}): {response.summary} "
                                    f"{document['note']}".strip()})
    elif action == "ask":
        messages.append({"role": "user", "content": question})
        edit_slot.button("Edit", key="edit", on_click=start_editing)
    else:  # a reply inside the drafting flow: no Edit button, not used as context for later questions
        messages.append({"role": "user", "content": question, "flow": True})
    messages.append({"role": "assistant", "response": response})
    save_current_chat()
    draw_topbar(busy=False)

# Chat history: read from / write to this browser's storage (must be the last thing on the page).
sync_history()
