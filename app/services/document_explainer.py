"""Explain a legal document (a notice, letter, summons...) in plain language, checked by code.

Steps:
  1. READ     PDF text with pypdf; a photo is transcribed by a vision model (shown to the user to check).
  2. LAWS     our code (not the model) finds every "section X of the Y Act" in the document and looks
              each one up in the Acts NyayaAI has. Laws we do not have are marked "not covered".
  3. EXPLAIN  the model explains the document using ONLY the document and the sections of law we give it.
  4. CHECK    our code checks that every quote from the document is really in it, that every date and
              amount in the explanation appears in the document (or, for amounts/durations, in the law
              given), and verifies every legal citation exactly like normal answers.
"""

import base64
import io
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app.services.answer_generator import DISCLAIMER, Citation, ModelRefusedError
from app.services.citation_verifier import (CitationCheck, adjust_confidence, normalise_for_matching,
                                            section_id, verify_citation)
from app.services.section_splitter import Section

MAX_DOCUMENT_CHARS = 15_000  # about 6 pages; longer documents are cut (and the user is told)
SEARCH_CONTEXT_SECTIONS = 6  # sections found by search, added after the ones the document names
MIN_DOCUMENT_CHARS = 40  # less text than this = nothing readable

# ---------------------------------------------------------------------------
# 1. Reading the document
# ---------------------------------------------------------------------------

TRANSCRIBE_PROMPT = """Copy ALL the text in this image exactly as written, line by line.
Do not correct spelling, translate, summarise or explain anything. Keep numbers, dates and amounts exactly.
Write [unclear] for any word you cannot read with confidence.
If the image contains no readable document text, reply with exactly: NO_TEXT"""


def read_pdf(data: bytes) -> str:
    """Text of a PDF that has real text in it (a scanned PDF has none: use a photo instead)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def read_image(data: bytes, mime_type: str, client, model: str) -> str:
    """Transcribe a photo of a document with a vision model. Returns "" if no text was found."""
    image_url = f"data:{mime_type};base64,{base64.b64encode(data).decode()}"
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": TRANSCRIBE_PROMPT},
            {"type": "input_image", "image_url": image_url},
        ]}],
        store=False,
    )
    text = (response.output_text or "").strip()
    return "" if text == "NO_TEXT" else text


# ---------------------------------------------------------------------------
# 2. Laws the document mentions (found by code, never by the model)
# ---------------------------------------------------------------------------


@dataclass
class LawMention:
    as_written: str  # e.g. "section 138 of the Negotiable Instruments Act, 1881"
    act: str  # the Act's name as written in the document, e.g. "Negotiable Instruments Act, 1881"
    section: str | None  # "138" (sub-sections like "(3)" stay in as_written); None = whole Act
    source_id: str | None  # our Act ID if NyayaAI has this Act, else None
    section_id: str | None  # "bnss_2023:35" if NyayaAI has this exact section, else None

    @property
    def covered(self) -> bool:
        return self.section_id is not None or (self.source_id is not None and self.section is None)


# An Act's name: starts with a capital letter, may contain small joining words ("of", "and"...),
# ends with Act / Sanhita / Code / Procedure, followed by the year. E.g. "Sexual Harassment of Women at
# Workplace (Prevention, Prohibition and Redressal) Act, 2013".
_WORD = r"[A-Z(][\w()',&.-]*"
_JOIN = r"(?:of|and|at|for|from|to|on|in|the)"
ACT_BODY = rf"[A-Z][\w()',&.-]*(?:\s+(?:{_WORD}|{_JOIN})){{0,14}}?\s+(?:Act|Sanhita|Code|Procedure)"
ACT = re.compile(rf"\b({ACT_BODY}),?\s*(\d{{4}})\b")
SECTION_REF = re.compile(
    rf"\b(?i:u/s|sections?)\b[.:\s]*(\d+[A-Z]?)((?:\s*\(\w{{1,4}}\))*)"
    rf"(?:\s+(?i:of)\s+(?:(?i:the)\s+)?(?:((?i:said\s+)?Act)\b(?!,?\s*\d{{4}})|({ACT_BODY}),?\s*(\d{{4}})\b))?"
)


def _name_key(name: str) -> str:
    """"The Bharatiya Nyaya Sanhita, 2023" and "Bharatiya Nyaya Sanhita 2023" -> the same key."""
    name = re.sub(r"^the\s+", "", name.strip(), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_law_mentions(text: str, sources: list[dict], sections: dict[str, Section]) -> list[LawMention]:
    """Every law the document refers to, in reading order, without duplicates.

    "section 11 of the said Act" / "section 16 of the Act" refer to the last Act named before them.
    An Act named without any section is listed once on its own.
    """
    flat = re.sub(r"\s+", " ", text)
    source_of = {_name_key(s["title"]): s["id"] for s in sources}

    events = sorted([(m.start(), "act", m) for m in ACT.finditer(flat)]
                    + [(m.start(), "section", m) for m in SECTION_REF.finditer(flat)], key=lambda e: e[0])

    mentions: dict[tuple, LawMention] = {}
    last_act = None
    acts_with_sections = set()
    for _, kind, m in events:
        if kind == "act":
            name = f"{m.group(1)}, {m.group(2)}"
            last_act = name
            mentions.setdefault(("act", _name_key(name)),
                                LawMention(name, name, None, source_of.get(_name_key(name)), None))
            continue
        number, sub = m.group(1).upper(), re.sub(r"\s+", "", m.group(2) or "")
        if m.group(4):
            act = last_act = f"{m.group(4)}, {m.group(5)}"
        else:
            act = last_act  # "of the said Act", "of the Act", or no Act named: the last Act named
        source_id = source_of.get(_name_key(act)) if act else None
        sid = f"{source_id}:{number}" if source_id else None
        if sid not in sections:
            sid = None  # NyayaAI has the Act but not this section number (or not the Act at all)
        key = ("section", _name_key(act or ""), number)
        if key not in mentions:
            mentions[key] = LawMention(m.group(0).strip(), act or "(Act not named)", number + sub, source_id, sid)
        if act:
            acts_with_sections.add(_name_key(act))

    return [m for key, m in mentions.items() if not (key[0] == "act" and key[1] in acts_with_sections)]


# ---------------------------------------------------------------------------
# 3. The explanation (Structured Outputs)
# ---------------------------------------------------------------------------


class DocumentQuote(BaseModel):
    quote: str = Field(description="Words copied EXACTLY from the DOCUMENT")
    meaning: str = Field(description="What this means for the reader, in plain language")


class DocumentExplanation(BaseModel):
    document_type: str = Field(description="What kind of document this is, in a few words")
    summary: str = Field(description="Who sent it, to whom, what it says and what it asks the reader to do")
    deadlines_and_amounts: list[DocumentQuote] = Field(
        description="EVERY deadline, date, time and amount of money in the DOCUMENT")
    key_points: list[DocumentQuote] = Field(description="The 2-5 most important demands, claims or warnings")
    law_explanation: str = Field(description="What the SOURCES say about the laws involved, with [section_id] tags")
    citations: list[Citation] = Field(description="One entry per legal statement in law_explanation")
    next_steps: list[str] = Field(description="Practical next steps for the reader")
    confidence: Literal["high", "medium", "low", "insufficient"] = Field(
        description="'insufficient' if this is not a legal document or cannot be understood")


EXPLAIN_PROMPT = """You are NyayaAI. A person in India has received the DOCUMENT below and wants to understand it.
You also receive LAWS MENTIONED (found by our code) and SOURCES: sections of Indian Acts, each with an ID in [brackets].

Rules you must always follow:
1. Use ONLY the DOCUMENT and the SOURCES. Never use your own memory of the law. Never name laws, sections, \
procedures, deadlines, fees or penalties that are not in the DOCUMENT or the SOURCES.
2. deadlines_and_amounts: list EVERY deadline, date, time and amount of money in the DOCUMENT. Each "quote" \
must be copied word for word from the DOCUMENT (for example "within 15 days of receipt of this notice").
3. key_points: the 2-5 most important demands, allegations or warnings, each quoted word for word from the DOCUMENT.
4. What the DOCUMENT claims is the sender's claim, not a proven fact. Never say whether the reader did anything \
wrong or whether the claims are true; that is decided by a court or the proper authority. Be calm and neutral.
5. For a law marked NOT AVAILABLE in LAWS MENTIONED: say clearly that NyayaAI does not have that law's text, and \
do NOT explain what it says, what it requires or its penalties.
6. law_explanation: explain in plain words what the SOURCES say that matters for this DOCUMENT. Every legal \
statement needs a citation: the section ID exactly as written in the SOURCES and a quote copied word for word \
from that section. If no SOURCES are relevant, say so and give no legal statements.
7. Do not write any date, deadline or amount of money that is not in the DOCUMENT or the SOURCES. Never calculate \
a final date yourself (for example "15 days from today"); explain how the DOCUMENT counts it instead.
8. Next steps must be practical: keep the document safe, note the deadline, do not ignore it, gather documents, \
and consult a qualified lawyer before the deadline. Never promise an outcome. Do not write helpline numbers.
9. Write in the same language as the person's NOTE (English if there is no note). Quotes always stay exactly as written.
10. If the DOCUMENT is not a legal or official document, or cannot be understood, say so and set confidence to "insufficient"."""


def build_laws_text(mentions: list[LawMention]) -> str:
    if not mentions:
        return "None found by our code."
    lines = []
    for m in mentions:
        if m.section_id:
            lines.append(f"- {m.as_written}: AVAILABLE, see SOURCES [{m.section_id}]")
        elif m.source_id and m.section is None:
            lines.append(f"- {m.as_written}: AVAILABLE (whole Act named, no section given)")
        elif m.source_id:
            lines.append(f"- {m.as_written}: NyayaAI has this Act but NOT this section number")
        else:
            lines.append(f"- {m.as_written}: NOT AVAILABLE (NyayaAI does not have this Act)")
    return "\n".join(lines)


def build_sources_block(sections: list[Section]) -> str:
    return "\n\n---\n\n".join(f"[{section_id(s)}] {s.citation} - {s.heading}\n{s.text}" for s in sections)


# ---------------------------------------------------------------------------
# 4. Checks done by code
# ---------------------------------------------------------------------------

MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + MONTHS + r")\.?,?\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(" + MONTHS + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b"),
]
AMOUNT = re.compile(r"(?:rs\.?|inr|₹)\s*(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*(?:rupees|/-)", re.IGNORECASE)
# Numbers written as words count too: an invented "thirty days" must be caught like "30 days".
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
NUMBER_WORDS.update({"thirty": 30, "forty": 40, "forty-five": 45, "fifty": 50, "sixty": 60, "seventy": 70,
                     "eighty": 80, "ninety": 90, "hundred": 100})
_NUMBER = r"\d+|" + "|".join(sorted(map(re.escape, NUMBER_WORDS), key=len, reverse=True))
DURATION = re.compile(rf"\b({_NUMBER})\s+(working\s+days|days?|weeks?|months?|years?|hours?)\b", re.IGNORECASE)


def _number(text: str) -> int:
    text = text.lower()
    return int(text) if text.isdigit() else NUMBER_WORDS[text]
CLOCK = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*(am|pm|a\.m\.|p\.m\.)?", re.IGNORECASE)


def _dates(text: str) -> set[tuple]:
    found = set()
    for pattern in DATE_PATTERNS[:2]:
        for m in pattern.finditer(text):
            groups = m.groups()
            day, month, year = (groups[0], groups[1], groups[2]) if groups[0].isdigit() else (groups[1], groups[0], groups[2])
            found.add((int(day), month[:3].lower(), int(year)))
    for m in DATE_PATTERNS[2].finditer(text):
        found.add(("numeric", int(m.group(1)), int(m.group(2)), int(m.group(3)) % 100))
    return found


def _amounts(text: str) -> set[str]:
    return {(m.group(1) or m.group(2)).replace(",", "").rstrip(".") for m in AMOUNT.finditer(text)}


def _durations(text: str) -> set[tuple]:
    return {(_number(m.group(1)), m.group(2).lower().split()[-1].rstrip("s"), "working" in m.group(2).lower())
            for m in DURATION.finditer(text)}


def _clocks(text: str) -> set[tuple]:
    return {(int(m.group(1)), m.group(2)) for m in CLOCK.finditer(text) if m.group(3)}


@dataclass
class FigureCheck:
    """A date, amount, duration or time written in the explanation, and whether we found it."""

    kind: str  # "date" | "amount" | "duration" | "time"
    text: str
    found: bool


def check_figures(explanation_text: str, document: str, law_text: str) -> list[FigureCheck]:
    """Every date/amount/duration/time in NyayaAI's own words must come from the document.

    Amounts and durations may also come from the law text we gave the model (e.g. "21 days" in a section).
    Dates and clock times must be in the document.
    """
    checks = []
    doc_dates, doc_amounts, law_amounts = _dates(document), _amounts(document), _amounts(law_text)
    doc_durations, law_durations, doc_clocks = _durations(document), _durations(law_text), _clocks(document)
    for pattern in DATE_PATTERNS:
        for m in pattern.finditer(explanation_text):
            checks.append(FigureCheck("date", m.group(0), bool(_dates(m.group(0)) & doc_dates)))
    for m in AMOUNT.finditer(explanation_text):
        value = (m.group(1) or m.group(2)).replace(",", "").rstrip(".")
        checks.append(FigureCheck("amount", m.group(0).strip(), value in doc_amounts | law_amounts))
    for m in DURATION.finditer(explanation_text):
        checks.append(FigureCheck("duration", m.group(0), bool(_durations(m.group(0)) & (doc_durations | law_durations))))
    for m in CLOCK.finditer(explanation_text):
        if m.group(3):
            checks.append(FigureCheck("time", m.group(0).strip(), bool(_clocks(m.group(0)) & doc_clocks)))
    return checks


@dataclass
class QuoteCheck:
    quote: str
    meaning: str
    verified: bool  # the quote really is in the document


def check_document_quote(quote: str, document: str) -> bool:
    normalised = normalise_for_matching(quote)
    return len(normalised) >= 4 and normalised in normalise_for_matching(document)


# ---------------------------------------------------------------------------
# The whole pipeline
# ---------------------------------------------------------------------------


@dataclass
class DocumentResponse:
    document_type: str
    summary: str
    deadlines_and_amounts: list[QuoteCheck]
    key_points: list[QuoteCheck]
    laws: list[LawMention]
    law_explanation: str
    citations: list[CitationCheck]
    next_steps: list[str]
    figures: list[FigureCheck]  # dates/amounts NyayaAI wrote, and whether each was found
    confidence: str
    model_confidence: str
    document_text: str  # what NyayaAI read (shown so the user can check it)
    truncated: bool
    sources_considered: list[str]
    disclaimer: str = DISCLAIMER
    input_tokens: int = 0
    output_tokens: int = 0
    kind: str = "document"
    from_photo: bool = False  # text was read from a photo by a model: reading mistakes are possible
    file_name: str = ""

    @property
    def unverified_figures(self) -> list[FigureCheck]:
        return [f for f in self.figures if not f.found]


class DocumentUnreadable(Exception):
    """No usable text could be read from the file. The message is shown to the user."""


class DocumentExplainer:
    def __init__(self, client, model: str, sources: list[dict], sections: list[Section], retriever=None,
                 vision_model: str | None = None):
        self.client = client
        self.model = model
        self.vision_model = vision_model or model
        self.sources = sources
        self.sections = {section_id(s): s for s in sections}
        self.retriever = retriever  # optional: search for related sections (e.g. remedies)

    def explain_file(self, data: bytes, mime_type: str, file_name: str, note: str = "") -> DocumentResponse:
        """Read a PDF or a photo, then explain it."""
        is_pdf = mime_type == "application/pdf" or file_name.lower().endswith(".pdf")
        if is_pdf:
            text = read_pdf(data)
            if len(text) < MIN_DOCUMENT_CHARS:
                raise DocumentUnreadable("This PDF has no readable text (it is probably a scan). "
                                         "Please take a clear photo of the page instead.")
        else:
            text = read_image(data, mime_type or "image/jpeg", self.client, self.vision_model)
            if len(text) < MIN_DOCUMENT_CHARS:
                raise DocumentUnreadable("NyayaAI could not read any document text in this photo. Try a sharper "
                                         "photo in good light, with the whole page flat and visible.")
        response = self.explain(text, note)
        response.from_photo, response.file_name = not is_pdf, file_name
        return response

    def explain(self, document_text: str, note: str = "") -> DocumentResponse:
        truncated = len(document_text) > MAX_DOCUMENT_CHARS
        document = document_text[:MAX_DOCUMENT_CHARS]

        mentions = find_law_mentions(document, self.sources, self.sections)
        context = [self.sections[m.section_id] for m in mentions if m.section_id]
        if self.retriever is not None:
            for result in self.retriever.search(document[:3000], top_k=SEARCH_CONTEXT_SECTIONS):
                if section_id(result.section) not in {section_id(s) for s in context}:
                    context.append(result.section)

        user_message = (f"NOTE FROM THE PERSON:\n{note.strip() or '(none)'}\n\n"
                        f"DOCUMENT:\n<<<\n{document}\n>>>\n\n"
                        f"LAWS MENTIONED (found by our code):\n{build_laws_text(mentions)}\n\n"
                        f"SOURCES:\n\n{build_sources_block(context) or '(none)'}")
        response = self.client.responses.parse(model=self.model, instructions=EXPLAIN_PROMPT, input=user_message,
                                               text_format=DocumentExplanation, store=False)
        parsed = response.output_parsed
        if parsed is None:
            raise ModelRefusedError("The model did not return an explanation in the required format.")

        retrieved = {section_id(s): s for s in context}
        citations = [verify_citation(c.section_id, c.quote, c.supports, retrieved) for c in parsed.citations]
        law_text = "\n".join(s.text for s in context)
        own_words = "\n".join([parsed.document_type, parsed.summary, parsed.law_explanation, *parsed.next_steps,
                               *(q.meaning for q in parsed.deadlines_and_amounts + parsed.key_points),
                               *(c.supports for c in parsed.citations)])
        figures = check_figures(own_words, document, law_text)

        def quotes(items):
            return [QuoteCheck(q.quote, q.meaning, check_document_quote(q.quote, document)) for q in items]

        deadlines, key_points = quotes(parsed.deadlines_and_amounts), quotes(parsed.key_points)
        confidence = adjust_confidence(parsed.confidence, citations) if parsed.citations else parsed.confidence
        if confidence == "high" and (any(not f.found for f in figures)
                                     or any(not q.verified for q in deadlines + key_points)):
            confidence = "medium"
        return DocumentResponse(
            document_type=parsed.document_type, summary=parsed.summary, deadlines_and_amounts=deadlines,
            key_points=key_points, laws=mentions, law_explanation=parsed.law_explanation, citations=citations,
            next_steps=parsed.next_steps, figures=figures, confidence=confidence,
            model_confidence=parsed.confidence, document_text=document, truncated=truncated,
            sources_considered=[s.citation for s in context],
            input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
        )
