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
from app.services.answer_generator import ModelRefusedError
from app.services.document_explainer import DocumentUnreadable
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

/* Keep ☰ / Lady Justice / NyayaAI in ONE row on every screen. (On phones Streamlit stacks columns
   vertically, which made the pinned bar very tall and covered the page.) */
.st-key-topbar [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .6rem !important; }
.st-key-topbar [data-testid="stColumn"] { width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; }
.st-key-topbar [data-testid="stColumn"]:last-child { flex: 1 1 auto !important; }
@media (max-width: 640px) {
  .st-key-topbar { padding: .5rem 1rem 1.2rem; }
  .logo { height: 34px; }
  .st-key-brand button, .st-key-brand button p { font-size: 1.6rem !important; }
  .tagline { font-size: .72rem; margin-top: -.2rem; }
  .block-container { padding-top: 7.2rem; }  /* the tagline wraps to 2 lines on phones */
}
.block-container { padding-bottom: 7rem; max-width: 820px; }

/* --- top bar: menu button + NyayaAI (click = new chat) --- */
.st-key-brand button {
  background: transparent !important; border: none !important; box-shadow: none !important;
  font-family: 'Cormorant Garamond', serif !important; font-size: 2rem !important;
  letter-spacing: 0.06em; color: var(--text) !important; padding: 0 !important;
}
.st-key-brand button p { font-family: 'Cormorant Garamond', serif !important; font-size: 2rem !important; }
.st-key-brand button:hover { color: var(--accent) !important; }
.st-key-menu button { background: transparent !important; border: none !important; font-size: 1.4rem; }
/* Remove the small "⌄" arrow next to ☰ completely: merely hiding it still reserved 16px,
   which squeezed the ☰ itself to 0px wide (invisible) once the column got narrower. */
.st-key-menu button span:has(> [data-testid="stIconMaterial"]) { display: none !important; }
.st-key-menu button [data-testid="stMarkdownContainer"] { min-width: 1.3rem; overflow: visible; }
.st-key-menu button p { font-size: 1.4rem !important; line-height: 1; }
iframe { border: none; }
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


def quote_cards(items) -> str:
    """Quotes from the user's document, each with its meaning. Unverified ones are marked."""
    cards = []
    for q in items:
        mark = "" if q.verified else ' <span class="unverified">(these exact words were not found in your document)</span>'
        cards.append(f'<div class="step"><b>"{html.escape(q.quote)}"</b>{mark}<br>{html.escape(q.meaning)}</div>')
    return "".join(cards)


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
        st.markdown('<div class="section-title">Dates, deadlines and amounts</div>'
                    + quote_cards(response.deadlines_and_amounts), unsafe_allow_html=True)
    if response.key_points:
        st.markdown('<div class="section-title">What it says</div>' + quote_cards(response.key_points),
                    unsafe_allow_html=True)
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


def show_any_answer(response, animate: bool = False) -> None:
    if getattr(response, "kind", "") == "document":
        show_document_answer(response, animate)
    else:
        show_answer(response, animate)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.markdown(STYLE, unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

# Top bar: ☰ opens "about NyayaAI"; clicking the name starts a new chat.
# Wrapped in a container that CSS pins to the top of the window (stays visible when scrolling).
with st.container(key="topbar"):
    menu_col, logo_col, brand_col = st.columns([0.9, 0.6, 10.5], vertical_alignment="center")
    with logo_col:
        st.markdown(f'<img class="logo" src="data:image/png;base64,{LADY_ICON}" alt="Lady Justice">',
                    unsafe_allow_html=True)
    with menu_col:
        with st.popover("☰", key="menu"):
            areas = " and ".join(f"**{DOMAINS[d]['label']}** ({DOMAINS[d]['covers']})" for d in config.ENABLED_DOMAINS)
            st.markdown(f"**About NyayaAI**  \nPlain-language help with Indian {areas}, answered only from the "
                        "official text of the Acts (India Code). Every quote is checked against the Act.")
            st.markdown(f"**The {len(ENABLED_SOURCES)} Acts NyayaAI uses**")
            st.markdown("\n".join(f"- {s['title']} (as on {s['version_as_on']})" for s in ENABLED_SOURCES))
            st.markdown("**Not covered yet:** rules, fees, court judgments, state laws, and other areas of law "
                        "(property, family, tenancy, consumer, employment...).")
            st.markdown("**Privacy:** your questions are sent to OpenAI to write the answer. Do not include names, "
                        "phone numbers, addresses or other details that could identify you or anyone else. "
                        "NyayaAI does not save your conversation.")
            st.markdown("You can write in English, Hindi or Hinglish, speak your question (microphone), or attach "
                        "a notice or letter (PDF or photo) to have it explained.")
            st.markdown("**Documents and voice:** attached documents and recordings are also sent to OpenAI. "
                        "Documents often contain names and addresses; cover them if you can. "
                        "Nothing is saved by NyayaAI.")
    with brand_col:
        if st.button("NyayaAI", key="brand", help="Start a new conversation"):
            st.session_state.messages = []
            st.rerun()
    st.markdown('<div class="tagline">Legal information, not legal advice. For decisions, consult a qualified lawyer.</div>',
                unsafe_allow_html=True)

if not config.OPENAI_API_KEY:
    st.error("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key, then restart.")
    st.stop()

# Optional access code for the public demo (set APP_ACCESS_CODE as a secret on the host):
# the page is public, but every question is paid from the owner's OpenAI account.
if config.APP_ACCESS_CODE and not st.session_state.get("access_ok"):
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

# Earlier messages of this conversation (no animation when shown again).
messages = st.session_state.messages
last_user = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=None)
for index, message in enumerate(messages):
    if message["role"] == "assistant":
        with st.chat_message("assistant", avatar=SPHERE_ICON):
            show_any_answer(message["response"])
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
                    st.session_state.pending_question = edited.strip()
                    st.rerun()
                if cancel_col.button("Cancel", key="cancel_edit"):
                    st.session_state.editing = False
                    st.rerun()
            else:
                st.markdown(message["content"])
                if message.get("attachment"):
                    st.caption(f"Attached: {message['attachment']}")
                elif index == last_user and not question:  # a new question gets its own Edit button
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


def status_pill(seconds: int, text: str = THINKING_TEXT) -> str:
    return (f'<div class="hero"><div class="status"><span class="dot"></span>{text}'
            f'<span class="secs">{seconds}s</span></div></div>')


if question:
    # Thinking: on the first question the big sphere pulses ABOVE the question;
    # on follow-ups the small sphere pulses below it. Both show a Stop button.
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
            st.markdown(f'<div class="thinking-row">{sphere_html("small")}</div>', unsafe_allow_html=True)
            status = st.empty()
            st.button("Stop", key="stop")

    # Remember the question until its answer is shown: if the page reloads first, it is marked "stopped".
    st.session_state.in_progress = question
    try:
        if document:
            explainer = load_explainer()
            job = background_workers().submit(explainer.explain_file, document["data"], document["type"],
                                              document["name"], document["note"])
            thinking_text = DOCUMENT_THINKING_TEXT
        else:
            assistant = load_assistant()
            job = background_workers().submit(assistant.ask, question_with_context(messages, question))
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
        st.stop()
    except (openai.APIError, ModelRefusedError):
        st.session_state.pop("in_progress", None)
        thinking.empty()
        st.error("Sorry, the AI service could not answer right now. Please try again in a moment.")
        st.stop()
    except Exception:  # e.g. a damaged PDF; the full error goes to the server log, not the page
        logging.getLogger("nyayaai").exception("Could not process the attached document")
        st.session_state.pop("in_progress", None)
        thinking.empty()
        st.error("Sorry, NyayaAI could not read this file. Please try a PDF or a clear photo of the page.")
        st.stop()
    st.session_state.pop("in_progress", None)

    # Answer ready: the big sphere shrinks away and reappears as the small icon beside the answer.
    if first_question and TYPEWRITER_DELAY > 0:
        with thinking.container():
            show_sphere("collapse", size=340)
        time.sleep(0.8)
    thinking.empty()

    with st.chat_message("assistant", avatar=SPHERE_ICON):
        show_any_answer(response, animate=True)

    if document:
        # Follow-up questions ("what should I reply?") get a short description of the document as context.
        messages.append({"role": "user", "content": question, "attachment": document["name"],
                         "context": f"I attached a document ({response.document_type}): {response.summary} "
                                    f"{document['note']}".strip()})
    else:
        messages.append({"role": "user", "content": question})
        edit_slot.button("Edit", key="edit", on_click=start_editing)
    messages.append({"role": "assistant", "response": response})
