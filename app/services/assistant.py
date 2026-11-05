"""The full NyayaAI pipeline: retrieve sections -> generate answer -> verify citations."""

import json
from dataclasses import dataclass
from pathlib import Path

from app.services.answer_generator import DISCLAIMER, generate_answer
from app.services.citation_verifier import CitationCheck, adjust_confidence, section_id, verify_citation


@dataclass
class AssistantResponse:
    question: str
    answer: str
    confidence: str  # after verification (may be lower than the model's own)
    model_confidence: str  # what the model itself said
    citations: list[CitationCheck]
    next_steps: list[str]
    disclaimer: str
    sources_considered: list[str]  # every section given to the model
    model: str
    input_tokens: int
    output_tokens: int


def load_known_issues(sources_file: Path) -> dict[str, list[str]]:
    """Read the known_issues of every source in sources.json, keyed by source id."""
    sources = json.loads(sources_file.read_text(encoding="utf-8"))["sources"]
    return {source["id"]: source.get("known_issues", []) for source in sources}


def answer_question(
    question: str,
    retriever,
    client,
    model: str,
    known_issues: dict[str, list[str]],
    context_sections: int = 8,
) -> AssistantResponse:
    # 1. Retrieve: find the sections most relevant to the question.
    results = retriever.search(question, top_k=context_sections)

    # 2. Generate: the model answers using only those sections.
    generated = generate_answer(question, results, known_issues, client=client, model=model)

    # 3. Verify: our code checks every citation against the retrieved text.
    retrieved = {section_id(r.section): r.section for r in results}
    checks = [
        verify_citation(c.section_id, c.quote, c.supports, retrieved)
        for c in generated.answer.citations
    ]

    return AssistantResponse(
        question=question,
        answer=generated.answer.answer,
        confidence=adjust_confidence(generated.answer.confidence, checks),
        model_confidence=generated.answer.confidence,
        citations=checks,
        next_steps=generated.answer.next_steps,
        disclaimer=DISCLAIMER,
        sources_considered=[r.section.citation for r in results],
        model=generated.model,
        input_tokens=generated.input_tokens,
        output_tokens=generated.output_tokens,
    )
