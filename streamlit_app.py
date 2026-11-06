"""NyayaAI chat page.

Run from the project root:
    streamlit run streamlit_app.py
"""

import json
import re
from pathlib import Path

import openai
import streamlit as st

from app import config
from app.domains import load_domains
from app.services.answer_generator import ModelRefusedError

ROOT = Path(__file__).parent
SOURCES = json.loads((ROOT / "data/legal_sources/sources.json").read_text(encoding="utf-8"))["sources"]
DOMAINS = load_domains(ROOT / "data/legal_sources/domains.json")
ENABLED_SOURCES = [s for s in SOURCES if s["domain"] in config.ENABLED_DOMAINS]
# "The Bharatiya Nyaya Sanhita, 2023" -> "Bharatiya Nyaya Sanhita 2023"
SHORT_NAME = {s["id"]: s["title"].removeprefix("The ").replace(",", "") for s in SOURCES}

st.set_page_config(page_title="NyayaAI", page_icon="⚖️")

CONFIDENCE_LABELS = {
    "high": "✅ Well supported by the text of the Acts",
    "medium": "🟡 Partly supported - some points need checking",
    "low": "🟠 Weakly supported - please check with a lawyer",
    "insufficient": "ℹ️ Not covered by the laws NyayaAI has",
}
EXAMPLES = {
    "ipr": [
        "Can someone use my YouTube video without my permission?",
        "Someone is using a logo very similar to mine. What can I do?",
        "क्या मैं अपने ब्रांड का नाम ट्रेडमार्क के रूप में रजिस्टर करा सकता हूँ?",
    ],
    "criminal": [
        "The police refused to register my FIR because the incident happened in another area. Is that allowed?",
        "Someone called pretending to be from my bank, got my OTP and took money. What can I do?",
    ],
}
PREVIOUS_TURNS_USED = 2  # earlier user messages added as context for follow-up questions

# Internal citation IDs in the answer text, e.g. "[copyright_act_1957:13]" or "[patents_act_1970:117A]"
CITATION_ID = re.compile(r"\[([a-z_]+_\d{4}):(\w+)\]")


@st.cache_resource(show_spinner="Loading the law and search models (about 20 seconds, first time only)...")
def load_assistant():
    """Build the pipeline once and reuse it for every visitor and every message."""
    from scripts.search import build_assistant

    return build_assistant()


def question_with_context(messages: list[dict], new_question: str) -> str:
    """Add the user's last few messages so follow-ups like 'what if it was only 10 seconds?' make sense."""
    earlier = [m["content"] for m in messages if m["role"] == "user"][-PREVIOUS_TURNS_USED:]
    if not earlier:
        return new_question
    context = "\n".join(f"- {text}" for text in earlier)
    return f"Earlier in this conversation the user said:\n{context}\n\nCurrent question: {new_question}"


def readable_citations(text: str) -> str:
    """Turn internal IDs like "[copyright_act_1957:13]" into "(Section 13, Copyright Act 1957)" for people."""
    def replace(match: re.Match) -> str:
        act = SHORT_NAME.get(match.group(1), match.group(1))  # "Copyright Act 1957"
        return f"(Section {match.group(2)}, {act})"

    return CITATION_ID.sub(replace, text)


def show_answer(response) -> None:
    """Display one NyayaAI answer with its citations."""
    notes = getattr(response, "safety_notes", [])
    for note in notes:
        if note.kind == "old_law":
            st.warning(f"**Date check:** {note.text}  \n*Source: {note.source}*")
    st.markdown(readable_citations(response.answer))
    st.caption(CONFIDENCE_LABELS.get(response.confidence, response.confidence))
    helplines = [n for n in notes if n.kind == "helpline"]
    if helplines:
        st.info("**Get help now**  \n" + "  \n".join(f"📞 {n.text} *(source: {n.source})*" for n in helplines))

    if response.citations:
        verified = sum(c.verified for c in response.citations)
        with st.expander(f"Sources: {verified} of {len(response.citations)} citations verified in the official text"):
            for c in response.citations:
                where = f"{c.citation}, page {c.page} of the India Code PDF" if c.citation else c.section_id
                if c.verified:
                    st.markdown(f"✅ **{where}**  \n> {c.quote}  \n*Supports:* {readable_citations(c.supports)}")
                else:
                    st.markdown(f"⚠️ **Could not verify** ({where}): {c.reason}  \n"
                                f"*Claim:* {readable_citations(c.supports)}")

    if response.next_steps:
        st.markdown("**What you can do next**")
        st.markdown("\n".join(f"- {readable_citations(step)}" for step in response.next_steps))
    st.caption(response.disclaimer)


# --- Sidebar -------------------------------------------------------------------------
with st.sidebar:
    st.header("⚖️ NyayaAI")
    areas = " and ".join(f"**{DOMAINS[d]['label']}** ({DOMAINS[d]['covers']})" for d in config.ENABLED_DOMAINS)
    st.write(f"Plain-language help with Indian {areas}, answered only from the official text of the Acts "
             "(India Code). Every quote is checked against the Act.")
    with st.expander(f"The {len(ENABLED_SOURCES)} Acts NyayaAI uses"):
        st.markdown("\n".join(f"- {s['title']} (as on {s['version_as_on']})" for s in ENABLED_SOURCES))
    st.write("**Not covered yet:** rules, fees, court judgments, state laws, and other areas of law "
             "(property, family, tenancy, consumer, employment...).")
    st.info("Privacy: your questions are sent to OpenAI to write the answer. Do not include names, "
            "phone numbers, addresses or other details that could identify you or anyone else. "
            "NyayaAI does not save your conversation.")
    st.write("You can write in English, Hindi or Hinglish.")
    st.write("**Try:**")
    for example in [e for d in config.ENABLED_DOMAINS for e in EXAMPLES.get(d, [])]:
        if st.button(example, use_container_width=True):
            st.session_state.pending_question = example
    if st.button("🗑️ New conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# --- Main chat -------------------------------------------------------------------------
st.title("NyayaAI")
st.caption("Legal information, not legal advice. For decisions, consult a qualified lawyer.")

if not config.OPENAI_API_KEY:
    st.error("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key, then restart.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            show_answer(message["response"])
        else:
            st.markdown(message["content"])

typed = st.chat_input("Describe your problem, e.g. 'Someone copied my song on Instagram'")
question = typed or st.session_state.pop("pending_question", None)

if question:
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            assistant = load_assistant()
            with st.spinner("Searching the Acts and checking citations..."):
                response = assistant.ask(question_with_context(st.session_state.messages, question))
        except (openai.APIError, ModelRefusedError):
            st.error("Sorry, the AI service could not answer right now. Please try again in a moment.")
            st.stop()
        show_answer(response)

    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.messages.append({"role": "assistant", "response": response})
