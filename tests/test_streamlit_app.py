"""Tests for the chat page (streamlit_app.py), run headless with a fake assistant."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import scripts.search
from app import config
from app.services.answer_generator import DISCLAIMER
from app.services.assistant import AssistantResponse
from app.services.citation_verifier import CitationCheck

# The page lives in the project root, one folder up from tests/
APP_FILE = str(Path(__file__).parent.parent / "streamlit_app.py")


class FakeAssistant:
    def __init__(self):
        self.questions = []

    def ask(self, question):
        self.questions.append(question)
        return AssistantResponse(
            question=question,
            answer="A patent lasts twenty years from the filing date. [patents_act_1970:53]",
            confidence="high",
            model_confidence="high",
            citations=[CitationCheck("patents_act_1970:53", "The term of every patent shall be twenty years",
                                     "A patent lasts twenty years", True, "Quote found in the section text.",
                                     "Section 53, The Patents Act, 1970", 30)],
            next_steps=["Check your filing date."],
            disclaimer=DISCLAIMER,
            sources_considered=["Section 53, The Patents Act, 1970"],
            model="test-model",
            input_tokens=1,
            output_tokens=1,
        )


@pytest.fixture
def fake(monkeypatch):
    assistant = FakeAssistant()
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("NYAYAAI_TYPEWRITER_DELAY", "0")  # no typing animation in tests
    monkeypatch.setattr(scripts.search, "build_assistant", lambda: assistant)
    st.cache_resource.clear()  # make the page build the (fake) assistant again
    yield assistant
    st.cache_resource.clear()


def all_text(at: AppTest) -> str:
    return " ".join(e.value for e in [*at.markdown, *at.caption] if isinstance(e.value, str))


def test_page_shows_error_without_api_key(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")

    at = AppTest.from_file(APP_FILE).run()

    assert "OPENAI_API_KEY is not set" in at.error[0].value


def test_question_gets_answer_with_confidence_and_steps(fake):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].set_value("How long does a patent last?").run()

    text = all_text(at)
    assert "A patent lasts twenty years" in text
    assert "(Section 53, Patents Act 1970)" in text  # readable, not "[patents_act_1970:53]"
    assert "[patents_act_1970:53]" not in text
    assert "Well supported" in text
    assert "Check your filing date." in text
    assert fake.questions == ["How long does a patent last?"]


def test_follow_up_question_includes_earlier_messages(fake):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].set_value("How long does a patent last?").run()
    at.chat_input[0].set_value("Can it be renewed?").run()

    follow_up = fake.questions[-1]
    assert "How long does a patent last?" in follow_up
    assert "Current question: Can it be renewed?" in follow_up


def test_safety_notes_and_criminal_citations_are_shown(fake, monkeypatch):
    from app.safety import SafetyNote

    original = fake.ask

    def ask_with_notes(question):
        response = original(question)
        response.answer = "Stalking is an offence. [bns_2023:78]"
        response.safety_notes = [
            SafetyNote("old_law", "Your question mentions a date before 1 July 2024.", "S.O. 850(E)"),
            SafetyNote("helpline", "Women Helpline 181 (24x7).", "https://missionshakti.wcd.gov.in"),
        ]
        return response

    monkeypatch.setattr(fake, "ask", ask_with_notes)
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].set_value("A man follows me every day since March 2023").run()

    assert "(Section 78, Bharatiya Nyaya Sanhita 2023)" in all_text(at)
    assert "date before 1 July 2024" in at.warning[0].value
    assert any("181" in box.value for box in at.info)


def test_start_screen_shows_sphere_then_disappears_after_a_question(fake):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    assert len(at.chat_message) == 0  # start screen: only the sphere, no messages

    at.chat_input[0].set_value("How long does a patent last?").run()
    assert len(at.chat_message) == 2  # the question and its answer
    assert "A patent lasts twenty years" in all_text(at)


def test_clicking_the_name_starts_a_new_conversation(fake):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].set_value("How long does a patent last?").run()
    at.button(key="brand").click().run()

    assert at.session_state.messages == []
    assert len(at.chat_message) == 0


def test_page_text_makes_no_invented_claims(fake):
    # The design mock-ups contained invented claims; none may appear on the real page.
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    text = all_text(at).lower()
    for claim in ["tflops", "encrypted", "sovereign", "precision", "inc.", "audit"]:
        assert claim not in text


def test_edit_replaces_the_latest_question_and_its_answer(fake):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].set_value("How long does a patant last?").run()
    at.button(key="edit").click().run()
    at.text_area(key="edit_box").set_value("How long does a patent last in India?")
    at.button(key="resend").click().run()

    assert fake.questions[-1] == "How long does a patent last in India?"
    users = [m["content"] for m in at.session_state.messages if m["role"] == "user"]
    assert users == ["How long does a patent last in India?"]  # the typo version and its answer are gone


def test_question_interrupted_by_stop_is_kept_and_marked_stopped(fake):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.session_state["in_progress"] = "A question that was being answered when Stop was clicked"
    at.run()

    roles = [m["role"] for m in at.session_state.messages]
    assert roles == ["user", "stopped"]
    assert "Stopped" in all_text(at)


def test_follow_up_context_keeps_four_questions_and_ignores_unrelated_topics(fake):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    for q in ["Q0 old topic", "Q1 youtube strike", "Q2 harassment", "Q3 stalking", "Q4 fir",
              "Q5 youtube claim again"]:
        at.chat_input[0].set_value(q).run()

    earlier, current = fake.questions[-1].split("Current question:")
    assert all(q in earlier for q in ["Q1 youtube strike", "Q2 harassment", "Q3 stalking", "Q4 fir"])
    assert "Q0 old topic" not in earlier  # only the last four earlier questions are kept
    assert "ignore them" in earlier
    assert current.strip() == "Q5 youtube claim again"


def test_answer_page_has_no_emojis(fake):
    # Owner's design choice: no emojis on the page (the ☰ menu symbol is not an emoji and is allowed).
    import re

    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].set_value("How long does a patent last?").run()
    shown = all_text(at) + " ".join(b.label for b in at.button)
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿■-◿️]")
    assert emoji.findall(shown.replace("☰", "")) == []


def test_access_code_is_required_when_set(fake, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_CODE", "lex-2026")
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    assert len(at.chat_input) == 0  # no question box before the code is entered

    at.text_input(key="access_code").set_value("wrong").run()
    assert "not correct" in at.error[0].value
    assert len(at.chat_input) == 0

    at.text_input(key="access_code").set_value("lex-2026").run()
    at.chat_input[0].set_value("How long does a patent last?").run()
    assert "A patent lasts twenty years" in all_text(at)


# --- Explain my document + voice (2026-11-07) ---------------------------------------------

from app.services.document_explainer import DocumentResponse, DocumentUnreadable, LawMention, QuoteCheck  # noqa: E402


class FakeExplainer:
    def __init__(self, from_photo=False, unreadable=False):
        self.calls, self.from_photo, self.unreadable = [], from_photo, unreadable

    def explain_file(self, data, mime_type, file_name, note=""):
        self.calls.append((file_name, mime_type, note))
        if self.unreadable:
            raise DocumentUnreadable("NyayaAI could not read any document text in this photo.")
        return DocumentResponse(
            document_type="Demand notice", summary="The sender asks you to pay the amount in the notice.",
            deadlines_and_amounts=[QuoteCheck("within 15 days of receipt of this notice", "Counted from receipt.", True)],
            key_points=[QuoteCheck("you owe me money", "Invented quote", False)],
            laws=[LawMention("section 138 of the Negotiable Instruments Act, 1881", "Negotiable Instruments Act, 1881",
                             "138", None, None)],
            law_explanation="NyayaAI does not have this law.", citations=[], next_steps=["Consult a lawyer."],
            figures=[], confidence="medium", model_confidence="medium", document_text="DEMAND NOTICE ...",
            truncated=False, sources_considered=[], from_photo=self.from_photo, file_name=file_name)


@pytest.fixture
def fake_explainer(fake, monkeypatch):
    fake.retriever = fake.client = None  # the page shares these with the explainer
    explainer = FakeExplainer()
    monkeypatch.setattr(scripts.search, "build_document_explainer", lambda **kwargs: explainer)
    return explainer


def test_attached_document_is_explained(fake_explainer):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].upload("notice.pdf", b"%PDF-1.4 fake", "application/pdf").run()

    text = all_text(at)
    assert fake_explainer.calls == [("notice.pdf", "application/pdf", "")]
    assert "Attached: notice.pdf" in text
    assert "Dates, deadlines and amounts" in text and "within 15 days of receipt of this notice" in text
    assert "not found in your document" in text  # the unverified quote is marked
    assert "does not have this law" in text  # NI Act s.138 is not covered
    assert not [b for b in at.button if b.key == "edit"]  # editing would only re-send text
    assert not at.warning  # a PDF, not a photo: no photo warning


def test_photo_gets_reading_warning(fake, monkeypatch):
    explainer = FakeExplainer(from_photo=True)
    fake.retriever = fake.client = None
    monkeypatch.setattr(scripts.search, "build_document_explainer", lambda **kwargs: explainer)
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].upload("notice.jpg", b"jpeg", "image/jpeg").run()
    assert "Read from a photo" in at.warning[0].value


def test_unreadable_photo_gives_friendly_message(fake, monkeypatch):
    explainer = FakeExplainer(unreadable=True)
    fake.retriever = fake.client = None
    monkeypatch.setattr(scripts.search, "build_document_explainer", lambda **kwargs: explainer)
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].upload("blurry.jpg", b"jpeg", "image/jpeg").run()
    assert "could not read" in at.warning[0].value
    assert not at.exception


def test_follow_up_after_document_knows_the_document(fake, fake_explainer):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.chat_input[0].upload("notice.pdf", b"%PDF-1.4 fake", "application/pdf").run()
    at.chat_input[0].set_value("What should I reply?").run()
    assert "I attached a document (Demand notice)" in fake.questions[-1]


def test_voice_text_is_checked_before_sending(fake):
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.session_state["heard"] = at.session_state["heard_box"] = "How long does a patent last?"
    at.run()
    assert at.text_area(key="heard_box").value == "How long does a patent last?"
    assert not fake.questions  # nothing is sent until the person presses Send

    at.text_area(key="heard_box").set_value("How long does a patent last in India?")
    at.button(key="send_heard").click().run()
    assert fake.questions == ["How long does a patent last in India?"]
