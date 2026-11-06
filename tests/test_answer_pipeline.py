"""Tests for answer_generator.py and assistant.py, using a FAKE OpenAI client.

No real API calls: free, fast, and no API key needed.
"""

from types import SimpleNamespace

import pytest

from app.services.answer_generator import (
    DISCLAIMER,
    Citation,
    LegalAnswer,
    ModelRefusedError,
    build_sources_text,
    generate_answer,
)
from app.services.assistant import answer_question
from app.services.retriever import SearchResult
from app.services.section_splitter import Section

SECTION = Section(
    source_id="patents_act_1970",
    act_title="The Patents Act, 1970",
    section="53",
    heading="Term of patent",
    status="in_force",
    chapter=None,
    page_start=30,
    page_end=30,
    text="53. Term of patent.—The term of every patent shall be twenty years from the date of filing.",
    citation="Section 53, The Patents Act, 1970",
)
RESULTS = [SearchResult(section=SECTION, score=1.0)]


class FakeResponses:
    """Imitates client.responses: records the request and returns a prepared answer."""

    def __init__(self, parsed):
        self.parsed = parsed
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200)
        return SimpleNamespace(output_parsed=self.parsed, usage=usage)


class FakeClient:
    def __init__(self, parsed):
        self.responses = FakeResponses(parsed)


class FakeRetriever:
    def search(self, question, top_k=5):
        return RESULTS


def model_answer(citations, confidence="high") -> LegalAnswer:
    return LegalAnswer(
        answer="A patent lasts twenty years from the filing date.",
        citations=citations,
        confidence=confidence,
        next_steps=["Check your filing date."],
    )


# --- building the prompt ----------------------------------------------------


def test_sources_text_contains_id_citation_text_and_known_issues():
    text = build_sources_text(RESULTS, known_issues={"patents_act_1970": ["Example issue."]})

    assert "[patents_act_1970:53] Section 53, The Patents Act, 1970 - Term of patent" in text
    assert "KNOWN ISSUE with this Act's text: Example issue." in text
    assert "twenty years from the date of filing" in text


def test_generate_answer_sends_rules_question_and_sources():
    client = FakeClient(model_answer([]))

    generate_answer("How long does a patent last?", RESULTS, {}, client=client, model="test-model",
                    instructions="TEST RULES")
    request = client.responses.request

    assert request["model"] == "test-model"
    assert request["instructions"] == "TEST RULES"
    assert "How long does a patent last?" in request["input"]
    assert "[patents_act_1970:53]" in request["input"]
    assert request["text_format"] is LegalAnswer
    assert request["store"] is False


def test_refusal_raises_an_error():
    with pytest.raises(ModelRefusedError):
        generate_answer("question", RESULTS, {}, client=FakeClient(parsed=None), model="m", instructions="r")


# --- the full pipeline --------------------------------------------------------


def ask(citations, confidence="high"):
    return answer_question(
        "How long does a patent last?",
        retriever=FakeRetriever(),
        client=FakeClient(model_answer(citations, confidence)),
        model="test-model",
        known_issues={},
        system_prompt="TEST RULES",
    )


def test_pipeline_verifies_a_genuine_citation():
    response = ask([Citation(section_id="patents_act_1970:53",
                             quote="The term of every patent shall be twenty years",
                             supports="A patent lasts twenty years")])

    assert response.citations[0].verified
    assert response.confidence == "high"
    assert response.disclaimer == DISCLAIMER
    assert response.sources_considered == ["Section 53, The Patents Act, 1970"]
    assert (response.input_tokens, response.output_tokens) == (1000, 200)


def test_pipeline_rejects_a_hallucinated_citation_and_lowers_confidence():
    response = ask([Citation(section_id="patents_act_1970:999",
                             quote="The term of every patent shall be fifty years",
                             supports="A patent lasts fifty years")])

    assert not response.citations[0].verified
    assert response.model_confidence == "high"
    assert response.confidence == "low"


def test_pipeline_adds_safety_notes_from_verified_citations_only():
    from app.safety import load_safety
    from pathlib import Path

    safety = load_safety(Path(__file__).parent.parent / "data/legal_sources/safety.json")
    response = answer_question(
        "How long does a patent last? It happened in March 2023.",
        retriever=FakeRetriever(),
        client=FakeClient(model_answer([Citation(section_id="patents_act_1970:53",
                                                 quote="The term of every patent shall be twenty years",
                                                 supports="A patent lasts twenty years")])),
        model="test-model",
        known_issues={},
        system_prompt="TEST RULES",
        safety=safety,
        domain_of={"patents_act_1970": "ipr"},
    )
    # IPR citation: no helplines, and no old-criminal-law notice even though the question has a 2023 date
    assert response.safety_notes == []
