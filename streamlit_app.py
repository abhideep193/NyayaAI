"""NyayaAI chat page.

Run from the project root:
    streamlit run streamlit_app.py
"""

import re

import openai
import streamlit as st

from app import config
from app.services.answer_generator import ModelRefusedError

st.set_page_config(page_title="NyayaAI", page_icon="⚖️")

CONFIDENCE_LABELS = {
    "high": "✅ Well supported by the text of the Acts",
    "medium": "🟡 Partly supported - some points need checking",
    "low": "🟠 Weakly supported - please check with a lawyer",
    "insufficient": "ℹ️ Not covered by the laws NyayaAI has",
}
EXAMPLES = [
    "Can someone use my YouTube video without my permission?",
    "Someone is using a logo very similar to mine. What can I do?",
    "क्या मैं अपने ब्रांड का नाम ट्रेडमार्क के रूप में रजिस्टर करा सकता हूँ?",
]
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
        act = match.group(1).replace("_act_", " Act ").replace("_", " ").title()  # "Copyright Act 1957"
        return f"(Section {match.group(2)}, {act})"

    return CITATION_ID.sub(replace, text)


def show_answer(response) -> None:
    """Display one NyayaAI answer with its citations."""
    st.markdown(readable_citations(response.answer))
    st.caption(CONFIDENCE_LABELS.get(response.confidence, response.confidence))

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
    st.write(
        "Plain-language help with **copyright, trade marks and patents** in India, "
        "answered only from the official text of the Copyright Act 1957, Trade Marks Act 1999 "
        "and Patents Act 1970 (India Code). Every quote is checked against the Act."
    )
    st.write("**Not covered yet:** rules, fees, court judgments, and other areas of law "
             "(property, family, tenancy, consumer, employment...).")
    st.info("Privacy: your questions are sent to OpenAI to write the answer. "
            "Do not include names, phone numbers or other personal details.")
    st.write("You can write in English, Hindi or Hinglish.")
    st.write("**Try:**")
    for example in EXAMPLES:
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
