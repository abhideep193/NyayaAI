"""Check every citation in an LLM answer against the real law text. No AI involved.

A citation is VERIFIED only if:
  1. it cites a section we actually retrieved and gave to the model, and
  2. its quote really appears, word for word, in that section's text.
Anything else is REJECTED, so an invented section or invented quote cannot pass.
"""

import re
from dataclasses import dataclass

from app.services.section_splitter import Section

# Quotes shorter than this (after normalising) prove nothing, e.g. "the Act".
MIN_QUOTE_CHARS = 20


@dataclass
class CitationCheck:
    """The result of checking one citation."""

    section_id: str  # "copyright_act_1957:52"
    quote: str  # the words the model quoted
    supports: str  # the claim the quote is meant to support
    verified: bool
    reason: str  # why it was verified or rejected
    citation: str | None = None  # "Section 52, The Copyright Act, 1957" (if the section exists)
    page: int | None = None  # page of the official PDF


def section_id(section: Section) -> str:
    """The ID format used in the prompt: "<source_id>:<section number>"."""
    return f"{section.source_id}:{section.section}"


def normalise_for_matching(text: str) -> str:
    """Reduce text to a form where only the real words and punctuation matter.

    - Amendment markers like "3[" and "]" and omission stars "***" are removed.
    - Curly quotes/dashes become plain ones (models often type straight quotes).
    - ALL whitespace is removed. The PDF text contains split words such as
      "und er" for "under"; without spaces both become "under", so an honest
      quote still matches, while any changed letter still fails.
    - Lowercase, so capitalisation differences do not matter.
    """
    text = re.sub(r"\d+\[|\[|\]|\*", "", text)
    text = text.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-"}))
    text = re.sub(r"\s+", "", text)
    return text.lower()


def verify_citation(section_id_cited: str, quote: str, supports: str, retrieved: dict[str, Section]) -> CitationCheck:
    """Check one citation against the sections that were given to the model."""
    section = retrieved.get(section_id_cited)
    if section is None:
        return CitationCheck(
            section_id_cited, quote, supports, verified=False,
            reason="This section was not among the sections provided to the model.",
        )

    normalised_quote = normalise_for_matching(quote)
    details = {"citation": section.citation, "page": section.page_start}

    if len(normalised_quote) < MIN_QUOTE_CHARS:
        return CitationCheck(
            section_id_cited, quote, supports, verified=False,
            reason="Quote is too short to prove anything.", **details,
        )

    if normalised_quote not in normalise_for_matching(section.text):
        return CitationCheck(
            section_id_cited, quote, supports, verified=False,
            reason="Quoted words do not appear in this section's text.", **details,
        )

    return CitationCheck(
        section_id_cited, quote, supports, verified=True,
        reason="Quote found in the section text.", **details,
    )


def adjust_confidence(confidence: str, checks: list[CitationCheck]) -> str:
    """Lower the model's confidence if its citations did not survive verification.

    - No citation verified (but the model claimed an answer) -> "low"
    - Some citations rejected                                 -> at most "medium"
    """
    if confidence == "insufficient":
        return confidence
    verified = sum(check.verified for check in checks)
    if verified == 0:
        return "low"
    if verified < len(checks) and confidence == "high":
        return "medium"
    return confidence
