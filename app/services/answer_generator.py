"""Ask an OpenAI model to answer a legal question using ONLY the sections we retrieved."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.services.citation_verifier import section_id
from app.services.retriever import SearchResult

# ---------------------------------------------------------------------------
# The shape the model's reply MUST have (enforced by OpenAI Structured Outputs)
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    section_id: str = Field(description="The section ID exactly as given in the sources, e.g. copyright_act_1957:52")
    quote: str = Field(description="Words copied EXACTLY from that section's text that support the claim")
    supports: str = Field(description="The statement in the answer that this quote supports")


class LegalAnswer(BaseModel):
    answer: str = Field(description="Plain-language answer for a non-lawyer, based only on the sources")
    citations: list[Citation] = Field(description="One entry per legal claim in the answer")
    confidence: Literal["high", "medium", "low", "insufficient"] = Field(
        description="'insufficient' if the sources do not answer the question"
    )
    next_steps: list[str] = Field(description="Practical next steps the person could take")


# ---------------------------------------------------------------------------
# The instructions given to the model on every request
# ---------------------------------------------------------------------------

# {intro} and {scope} are filled in by app/domains.py from the enabled areas of law.
SYSTEM_PROMPT_TEMPLATE = """You are NyayaAI, an assistant that explains Indian {intro} \
to ordinary people in simple language.

You will receive a question and SOURCES: sections of Indian Acts, each with an ID in square brackets.

Rules you must always follow:
1. Use ONLY the SOURCES to state what the law says. Never rely on your own memory of the law, \
and never mention sections, Acts, rules or court cases that are not in the SOURCES.
2. Every legal statement in your answer needs a citation: the section ID exactly as written in the \
SOURCES, and a quote copied word for word from that section's text (a phrase or sentence, not a summary).
3. If the SOURCES do not answer the question, set confidence to "insufficient", say clearly that you \
cannot answer it from the laws available, and give no legal statements. If the question is about a \
different area of law (for example property, family, tenancy, employment or consumer problems) or is \
not a legal question at all, say that NyayaAI currently covers only {scope}, \
and suggest speaking to a qualified lawyer for that area. Do not name specific laws, sections, \
helplines or procedures for areas outside the SOURCES.
4. If a source has a KNOWN ISSUE note, take it into account and warn the user where relevant.
5. Write for someone with no legal training: short sentences, explain legal terms.
6. Next steps must be practical (e.g. what to document, which office or authority is involved, \
when to consult a lawyer). Do not invent fees, deadlines or procedures that are not in the SOURCES.
7. You give legal information, not legal advice. Do not tell the user what decision to make.
8. Write the answer, the "supports" statements and the next steps in the SAME language as the question \
(e.g. Hindi, Hinglish or English). But every quote must stay copied EXACTLY in English from the SOURCES, \
never translated, because quotes are checked word for word against the official text."""

# Added by our code (not the model) so it is always present and always worded the same.
DISCLAIMER = (
    "NyayaAI provides general legal information based on the text of Indian Acts, not legal advice. "
    "Laws change and every situation is different; please consult a qualified lawyer before acting."
)


def build_sources_text(results: list[SearchResult], known_issues: dict[str, list[str]]) -> str:
    """Format the retrieved sections as the SOURCES block of the prompt."""
    blocks = []
    for result in results:
        section = result.section
        lines = [f"[{section_id(section)}] {section.citation} - {section.heading}"]
        for issue in known_issues.get(section.source_id, []):
            lines.append(f"KNOWN ISSUE with this Act's text: {issue}")
        lines.append(section.text)
        blocks.append("\n".join(lines))
    return "\n\n---\n\n".join(blocks)


@dataclass
class GenerationResult:
    answer: LegalAnswer
    model: str
    input_tokens: int
    output_tokens: int


class ModelRefusedError(Exception):
    """The model refused to answer or returned no parsable answer."""


def generate_answer(
    question: str,
    results: list[SearchResult],
    known_issues: dict[str, list[str]],
    client,
    model: str,
    instructions: str,
) -> GenerationResult:
    """Send the question and sources to the model and return its structured answer.

    `client` is an openai.OpenAI() object (tests pass in a fake one).
    `instructions` is the system prompt built by app.domains.build_system_prompt().
    """
    user_message = (
        f"QUESTION:\n{question}\n\n"
        f"SOURCES:\n\n{build_sources_text(results, known_issues)}"
    )

    response = client.responses.parse(
        model=model,
        instructions=instructions,
        input=user_message,
        text_format=LegalAnswer,  # Structured Outputs: reply must match LegalAnswer
        store=False,  # ask OpenAI not to store this conversation for later retrieval
    )

    if response.output_parsed is None:
        raise ModelRefusedError("The model did not return an answer in the required format.")

    return GenerationResult(
        answer=response.output_parsed,
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
