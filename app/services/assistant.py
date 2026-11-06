"""The full NyayaAI pipeline: retrieve sections -> generate answer -> verify citations."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.safety import SafetyNote, safety_notes

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
    # Helplines / old-law notice added by our code (app/safety.py), not by the model.
    safety_notes: list[SafetyNote] = field(default_factory=list)


class NyayaAssistant:
    """Everything the pipeline needs, created once and reused for every question."""

    def __init__(self, retriever, client, model: str, known_issues: dict[str, list[str]],
                 system_prompt: str, context_sections: int = 8,
                 safety: dict | None = None, domain_of: dict[str, str] | None = None):
        self.retriever = retriever
        self.safety = safety  # contents of safety.json; None = no safety notes (e.g. in tests)
        self.domain_of = domain_of or {}  # source_id -> area of law
        self.system_prompt = system_prompt  # built from the enabled areas of law (app/domains.py)
        self.client = client
        self.model = model
        self.known_issues = known_issues
        self.context_sections = context_sections

    def ask(self, question: str) -> "AssistantResponse":
        return answer_question(
            question,
            retriever=self.retriever,
            client=self.client,
            model=self.model,
            known_issues=self.known_issues,
            system_prompt=self.system_prompt,
            context_sections=self.context_sections,
            safety=self.safety,
            domain_of=self.domain_of,
        )


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
    system_prompt: str,
    context_sections: int = 8,
    safety: dict | None = None,
    domain_of: dict[str, str] | None = None,
) -> AssistantResponse:
    # 1. Retrieve: find the sections most relevant to the question.
    results = retriever.search(question, top_k=context_sections)

    # 2. Generate: the model answers using only those sections.
    generated = generate_answer(question, results, known_issues, client=client, model=model,
                                instructions=system_prompt)

    # 3. Verify: our code checks every citation against the retrieved text.
    retrieved = {section_id(r.section): r.section for r in results}
    checks = [
        verify_citation(c.section_id, c.quote, c.supports, retrieved)
        for c in generated.answer.citations
    ]

    # 4. Safety: add checked helplines / old-law notice, based only on VERIFIED citations.
    verified_ids = [c.section_id for c in checks if c.verified]
    retrieved_ids = [section_id(r.section) for r in results]
    notes = safety_notes(question, verified_ids, domain_of or {}, safety, retrieved_ids) if safety else []

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
        safety_notes=notes,
    )
