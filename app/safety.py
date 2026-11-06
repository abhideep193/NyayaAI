"""Safety information added to answers by code, never by the model.

data/legal_sources/safety.json holds official helplines (each with its government source)
and the notice about the old criminal laws. Our code decides when to show them, using
only the VERIFIED citations, so the wording is always the same and always checked.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

# A year from 1900 to 2099 ...
YEAR = re.compile(r"\b(19\d\d|20\d\d)\b")
# ... unless it is part of a law's name, e.g. "Dowry Prohibition Act, 1961" or "Sanhita 2023".
LAW_NAME_BEFORE = re.compile(r"(act|code|sanhita|rules)\W{0,3}$", re.IGNORECASE)
# "March 2024", "15 Mar 2024", "03/2024", "15-03-2024"
MONTH_NAME_BEFORE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\W{0,3}$", re.IGNORECASE)
MONTH_NUMBER_BEFORE = re.compile(r"\b(\d{1,2})[/\-.]$")


@dataclass
class SafetyNote:
    kind: str  # "helpline" or "old_law"
    text: str
    source: str


def load_safety(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def mentions_date_before(question: str, cutoff: date) -> bool:
    """True if the question mentions a year (or month and year) before the cutoff date.

    Only digits are understood ("March 2023", "03/2024", "2019"); a Hindi month name
    or "last year" is not detected - a known limitation.
    """
    for match in YEAR.finditer(question):
        before = question[: match.start()]
        if LAW_NAME_BEFORE.search(before):
            continue
        year = int(match.group(1))
        if year < cutoff.year:
            return True
        if year == cutoff.year:
            month = None
            name = MONTH_NAME_BEFORE.search(before[-15:])
            number = MONTH_NUMBER_BEFORE.search(before[-6:])
            if name:
                month = MONTHS[name.group(1).lower()]
            elif number and 1 <= int(number.group(1)) <= 12:
                month = int(number.group(1))
            if month is not None and month < cutoff.month:
                return True
    return False


def helplines_for(verified_section_ids: list[str], safety: dict) -> list[SafetyNote]:
    """Helplines whose Acts (or specific sections) appear among the verified citations."""
    notes = []
    for helpline in safety["helplines"]:
        by_section = helpline.get("show_for_sections", {})
        for section_id in verified_section_ids:
            source_id, _, number = section_id.partition(":")
            if source_id in helpline.get("show_for_sources", []) or number in by_section.get(source_id, []):
                notes.append(SafetyNote("helpline", helpline["text"], helpline["source"]))
                break
    return notes


def keyword_helplines(question: str, safety: dict) -> list[SafetyNote]:
    """Helplines whose 'show_for_keywords' appear in the question (e.g. "OTP" -> cyber helpline 1930)."""
    text = question.lower()
    return [SafetyNote("helpline", h["text"], h["source"]) for h in safety["helplines"]
            if any(re.search(rf"\b{re.escape(k)}", text) for k in h.get("show_for_keywords", []))]


def safety_notes(question: str, verified_section_ids: list[str], domain_of: dict[str, str],
                 safety: dict, retrieved_section_ids: list[str] | None = None) -> list[SafetyNote]:
    """All safety notes for one answer. domain_of maps source_id -> domain (from sources.json).

    Helplines follow the VERIFIED citations. But a safety note must not disappear just because
    the model cited nothing (found 2026-11-06: an OTP-fraud answer citing BNS s.314 lost the 1930
    helpline; a March-2023 question with no citation lost the old-law notice). So when criminal law
    was SEARCHED for this question, the old-law notice and keyword helplines are also checked.
    """
    def domains(ids):
        return {domain_of.get(s.partition(":")[0]) for s in ids}

    notes = []
    old = safety["old_criminal_law"]
    criminal_areas = set(old["applies_to_domains"])
    criminal_searched = bool(domains(verified_section_ids + (retrieved_section_ids or [])) & criminal_areas)

    if criminal_searched and mentions_date_before(question, date.fromisoformat(old["new_laws_in_force_from"])):
        notes.append(SafetyNote("old_law", old["text"], old["source"]))

    helplines = helplines_for(verified_section_ids, safety)
    if criminal_searched:
        helplines += [h for h in keyword_helplines(question, safety) if h not in helplines]
    order = [h["text"] for h in safety["helplines"]]  # keep the order of safety.json
    return notes + sorted(helplines, key=lambda h: order.index(h.text))
