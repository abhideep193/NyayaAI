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
