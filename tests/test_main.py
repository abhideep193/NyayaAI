"""Tests for the API endpoints in app/main.py.

A fake assistant replaces the real one, so no models are loaded and no
OpenAI calls are made.
"""

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_assistant
from app.services.answer_generator import DISCLAIMER, ModelRefusedError
from app.services.assistant import AssistantResponse
from app.services.citation_verifier import CitationCheck

# One fake "browser" that all tests below use to call the app.
# (Not used as `with TestClient(app)`, so the real startup code never runs.)
client = TestClient(app)


class FakeAssistant:
    """Returns a fixed answer, or raises the error it was given."""

    def __init__(self, error: Exception | None = None):
        self.error = error

    def ask(self, question: str) -> AssistantResponse:
        if self.error:
            raise self.error
        return AssistantResponse(
            question=question,
            answer="A patent lasts twenty years from the filing date.",
            confidence="high",
            model_confidence="high",
            citations=[
                CitationCheck(
                    section_id="patents_act_1970:53",
                    quote="The term of every patent shall be twenty years",
                    supports="A patent lasts twenty years",
                    verified=True,
                    reason="Quote found in the section text.",
                    citation="Section 53, The Patents Act, 1970",
                    page=30,
                )
            ],
            next_steps=["Check your filing date."],
            disclaimer=DISCLAIMER,
            sources_considered=["Section 53, The Patents Act, 1970"],
            model="test-model",
            input_tokens=1000,
            output_tokens=200,
        )


def use_assistant(assistant) -> None:
    """Make /ask use `assistant` instead of the real one."""
    app.dependency_overrides[get_assistant] = lambda: assistant


@pytest.fixture(autouse=True)
def fake_assistant():
    """Runs around EVERY test: install a working fake assistant, then clean up."""
    use_assistant(FakeAssistant())
    yield
    app.dependency_overrides.clear()


def test_home_returns_welcome_message():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Welcome to NyayaAI!"


def test_ask_returns_structured_answer():
    response = client.post("/ask", json={"question": "How long does a patent last?"})
    body = response.json()

    assert response.status_code == 200
    assert body["question"] == "How long does a patent last?"
    assert body["confidence"] == "high"
    assert body["citations"][0]["verified"] is True
    assert body["citations"][0]["citation"] == "Section 53, The Patents Act, 1970"
    assert body["disclaimer"] == DISCLAIMER


def test_ask_rejects_too_short_question():
    # "Hi" has 2 characters; the minimum is 5
    response = client.post("/ask", json={"question": "Hi"})

    assert response.status_code == 422


def test_ask_rejects_too_long_question():
    # 2001 characters; the maximum is 2000
    response = client.post("/ask", json={"question": "a" * 2001})

    assert response.status_code == 422


def test_ask_rejects_missing_question():
    # Empty JSON body: the required "question" field is missing
    response = client.post("/ask", json={})

    assert response.status_code == 422


def test_ask_returns_503_when_assistant_is_not_configured():
    app.dependency_overrides.clear()  # use the real get_assistant; startup never ran

    response = client.post("/ask", json={"question": "How long does a patent last?"})

    assert response.status_code == 503


def test_ask_returns_502_when_openai_fails():
    error = openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
    use_assistant(FakeAssistant(error=error))

    response = client.post("/ask", json={"question": "How long does a patent last?"})

    assert response.status_code == 502
    assert "could not be reached" in response.json()["detail"]


def test_ask_returns_502_when_model_refuses():
    use_assistant(FakeAssistant(error=ModelRefusedError("refused")))

    response = client.post("/ask", json={"question": "How long does a patent last?"})

    assert response.status_code == 502
