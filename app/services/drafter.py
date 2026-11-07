"""Draft a letter or complaint, ONLY after the user agreed, from the answer NyayaAI already gave.

Two model calls, then checks by code:
  1. plan_draft():  choose the document type and ask for missing facts (never names/addresses/phones).
  2. write_draft(): write the draft from the user's own words and the law that was VERIFIED in the answer.
  3. code checks:   law references are verified word for word; section numbers or Act names in the letter
                    body are flagged; every date/amount/duration must come from the user's messages
                    (amounts/durations may also come from a verified quote); blanks are listed.

The filing guide that follows a draft is NOT written by the model: see app/filing_guides.py.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app.services.answer_generator import ModelRefusedError
from app.services.citation_verifier import CitationCheck, verify_citation
from app.services.document_explainer import FigureCheck, check_figures
from app.services.section_splitter import Section

# document type -> (label shown to the user, filing guide shown afterwards; None = legal-aid line only)
DOCUMENT_TYPES = {
    "consumer_complaint": ("Consumer complaint / refund demand", "consumer_complaint"),
    "landlord_letter": ("Letter to the landlord", "landlord_letter"),
    "police_complaint": ("Police complaint", "police_complaint"),
    "copyright_notice": ("Copyright infringement notice", "copyright_notice"),
    "legal_notice": ("Letter / notice to the other party", None),
}
GUIDES = ["consumer_complaint", "police_complaint", "cyber_complaint", "landlord_letter", "copyright_notice", "none"]
MAX_QUESTIONS = 4

DRAFT_LABEL = ("DRAFT prepared by NyayaAI: read it carefully, fill in every [BLANK], and change anything that is "
               "not exactly right before you use it. It is not legal advice; for an important matter, ask a lawyer "
               "to check it. NyayaAI does not send or file anything for you.")

# A blank the user must fill in: [YOUR NAME], [DATE OF PURCHASE], [NUMBER OF DAYS] ...
PLACEHOLDER = re.compile(r"\[[^\[\]\n]{2,60}\]")
# Law named inside the letter body: only allowed in the code-built "legal provisions" block.
LAW_IN_BODY = re.compile(r"\b(?:sections?|u/s)\s*\d|\bs\.\s*\d|\b(?:Act|Sanhita|Code),?\s+(?:of\s+)?(?:18|19|20)\d\d\b",
                         re.IGNORECASE)


# ---------------------------------------------------------------------------
# 1. Plan: which document, and which facts are missing
# ---------------------------------------------------------------------------


class DraftPlan(BaseModel):
    document_type: Literal[tuple(DOCUMENT_TYPES)] = Field(description="The document that fits the problem")
    guide: Literal[tuple(GUIDES)] = Field(
        description="Where it is sent or filed: consumer_complaint, police_complaint, cyber_complaint (online "
                    "fraud), landlord_letter, copyright_notice, or none")
    recipient: str = Field(description="Who the document is addressed to, in general words, e.g. 'the landlord'")
    questions: list[str] = Field(description=f"At most {MAX_QUESTIONS} short questions about facts that are "
                                             "missing AND would change the letter; empty if nothing is missing")


PLAN_PROMPT = """You help a person in India prepare a letter or complaint about the legal problem they described. \
NyayaAI has already explained the law to them, and they have agreed to get a draft.

Choose the document type and where it will go, and list the facts that are still MISSING.

Rules:
1. Ask only for facts that would change the letter: dates, amounts, what was promised, what happened, \
what they want (refund, replacement, removal...). Do not ask for something they already said.
2. NEVER ask for names, addresses, phone numbers, email addresses, ID numbers, account numbers or order \
numbers. The draft will keep blanks for those and the person fills them in themselves.
3. At most 4 questions, each short and simple. If nothing important is missing, return no questions.
4. Write the questions in the same language as the person's messages (English, Hindi or Hinglish).
5. Use "police_complaint" for crimes (theft, fraud, threats), with guide "cyber_complaint" for online or \
UPI/bank fraud. Use "legal_notice" if no other type fits."""


# ---------------------------------------------------------------------------
# 2. Write the draft
# ---------------------------------------------------------------------------


class LawReference(BaseModel):
    section_id: str = Field(description="Section ID exactly as given in LAW YOU MAY USE")
    quote: str = Field(description="Words copied EXACTLY from that section's text")
    relevance: str = Field(description="One short sentence: why this provision matters for this letter")


class DraftDocument(BaseModel):
    title: str = Field(description="e.g. 'Demand for refund of security deposit'")
    body: str = Field(description="The full letter or complaint, in plain formal English, with [BLANKS IN CAPITALS] "
                                  "for every missing detail. No section numbers or Act names in the body.")
    law_references: list[LawReference] = Field(description="Provisions from LAW YOU MAY USE that support the "
                                                           "letter; empty if none fits")
    check_before_sending: list[str] = Field(description="2-4 short points the person must check or decide before "
                                                        "using the draft, in the language of their messages")


WRITE_PROMPT = """You write a DRAFT letter or complaint for a person in India, from the facts THEY gave and \
the law that NyayaAI has already verified for them. They will review and complete it before using it.

Rules:
1. Use ONLY facts from the PERSON'S MESSAGES. Never invent a fact, name, date, amount, place, order number, \
phone number or event. Anything missing becomes a blank in square brackets and capitals, e.g. [YOUR NAME], \
[LANDLORD'S NAME], [ADDRESS OF THE FLAT], [DATE OF PURCHASE]. Always use blanks for the sender's and \
recipient's names, addresses and contact details, even if you could guess them.
2. Dates and amounts must be written exactly as the person gave them (you may write ₹50,000 as Rs. 50,000).
3. If the letter asks the other party to act by a deadline, write the deadline as a blank, e.g. \
"within [NUMBER OF DAYS] days", unless the person chose the number themselves. Do not take deadlines from the law.
4. Do NOT write section numbers or Act names in the body. Put the law ONLY in law_references, using section IDs \
and quotes copied EXACTLY from LAW YOU MAY USE. NyayaAI adds those to the letter itself after checking them. \
In the body you may say "under the applicable law" or "the provisions listed below".
5. Firm and polite. No threats the law does not support, no promise or prediction of the outcome, no insults.
6. The document is in English (it goes to a landlord, company or police). check_before_sending is in the \
same language as the person's messages.
7. Keep it short: one page. For a complaint, set out the facts in numbered paragraphs, then what is requested."""


@dataclass
class DraftResult:
    """A checked draft, ready to show (kind="draft")."""

    document_type: str
    label: str
    guide: str
    title: str
    body: str
    law: list[CitationCheck]  # every reference the model gave, with its check result
    blanks: list[str]
    figures: list[FigureCheck]
    law_in_body: list[str]  # section numbers / Act names the model wrote in the body (should be none)
    check_before_sending: list[str]
    kind: str = "draft"
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def verified_law(self) -> list[CitationCheck]:
        return [c for c in self.law if c.verified]

    @property
    def unverified_figures(self) -> list[FigureCheck]:
        return [f for f in self.figures if not f.found]

    @property
    def removed_law(self) -> list[CitationCheck]:
        return [c for c in self.law if not c.verified]

    def full_text(self) -> str:
        """The editable/downloadable text: title, body and the VERIFIED provisions (added by code)."""
        parts = [self.title.strip(), "", self.body.strip()]
        if self.verified_law:
            parts += ["", "Legal provisions referred to:"]
            parts += [f'- {c.citation}: "{clean_quote(c.quote)}"' for c in self.verified_law]
        return "\n".join(parts)


def clean_quote(quote: str) -> str:
    """For display in a letter: drop PDF line breaks and India Code amendment marks like "5[" and "]".

    Only layout changes; the words are the ones the verifier matched (it ignores the same marks).
    """
    quote = re.sub(r"\d+\[|\[|\]", "", quote)
    return re.sub(r"\s+", " ", quote).strip()


@dataclass
class DraftQuestions:
    """NyayaAI's questions before drafting (kind="draft_questions")."""

    plan: DraftPlan
    label: str
    kind: str = "draft_questions"


def _person_text(problem: str, consent: str, facts: str = "") -> str:
    return "\n".join(t for t in (problem, consent, facts) if t and t.strip())


class Drafter:
    def __init__(self, client, model: str, sections: dict[str, Section]):
        self.client = client
        self.model = model
        self.sections = sections  # section_id -> Section, every enabled Act

    def _parse(self, instructions: str, text: str, schema):
        response = self.client.responses.parse(model=self.model, instructions=instructions, input=text,
                                               text_format=schema, store=False)
        if response.output_parsed is None:
            raise ModelRefusedError("The model did not return a draft in the required format.")
        return response.output_parsed, response.usage

    def allowed_sections(self, answer) -> dict[str, Section]:
        """Only sections whose citation was VERIFIED in the answer may be used in the draft."""
        ids = [c.section_id for c in answer.citations if c.verified]
        return {i: self.sections[i] for i in ids if i in self.sections}

    def plan(self, problem: str, answer, consent: str = "") -> DraftQuestions:
        text = (f"PERSON'S PROBLEM:\n{problem}\n\nWHAT THEY SAID WHEN AGREEING TO A DRAFT:\n{consent or '(yes)'}\n\n"
                f"NYAYAAI'S ANSWER (already given to them):\n{answer.answer}")
        plan, _ = self._parse(PLAN_PROMPT, text, DraftPlan)
        plan.questions = [q for q in plan.questions if q.strip()][:MAX_QUESTIONS]
        return DraftQuestions(plan=plan, label=DOCUMENT_TYPES[plan.document_type][0])

    def write(self, problem: str, answer, plan: DraftPlan, consent: str = "", facts: str = "") -> DraftResult:
        allowed = self.allowed_sections(answer)
        law_block = "\n\n---\n\n".join(f"[{i}] {s.citation} - {s.heading}\n{s.text}" for i, s in allowed.items())
        person = _person_text(problem, consent, facts)
        text = (f"DOCUMENT TO WRITE: {DOCUMENT_TYPES[plan.document_type][0]}, addressed to {plan.recipient}\n\n"
                f"PERSON'S MESSAGES:\n{person}\n\n"
                f"NYAYAAI'S ANSWER (for background only; do not copy facts from it that the person did not say):\n"
                f"{answer.answer}\n\n"
                f"LAW YOU MAY USE:\n\n{law_block or '(none: leave law_references empty)'}")
        draft, usage = self._parse(WRITE_PROMPT, text, DraftDocument)

        law = [verify_citation(r.section_id, r.quote, r.relevance, allowed) for r in draft.law_references]
        verified_quotes = " ".join(c.quote for c in law if c.verified)
        body = draft.body
        return DraftResult(
            document_type=plan.document_type,
            label=DOCUMENT_TYPES[plan.document_type][0],
            guide=plan.guide,
            title=draft.title,
            body=body,
            law=law,
            blanks=list(dict.fromkeys(PLACEHOLDER.findall(draft.title + "\n" + body))),
            figures=check_figures(draft.title + "\n" + body, person, verified_quotes),
            law_in_body=[m.group(0) for m in LAW_IN_BODY.finditer(body)],
            check_before_sending=draft.check_before_sending,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )


# ---------------------------------------------------------------------------
# Consent typed in the chat ("yes", "haan, ...") instead of clicking the button
# ---------------------------------------------------------------------------

YES_WORDS = re.compile(
    r"^\s*(?:yes|yeah|yep|yup|sure|ok(?:ay)?|please|go ahead|haan?|haa+n?|han|ha+|ji|haan?\s*ji|hanji|bilkul|zaroor|"
    r"theek hai|thik hai|kar do|bana do|हाँ|हां|जी|ठीक है|ज़रूर|जरूर)(?=[\s,.!:;-]|$)", re.IGNORECASE)


def is_consent(text: str) -> bool:
    """True if a typed reply to NyayaAI's offer starts with yes/haan/ok... (the rest may add facts)."""
    return bool(YES_WORDS.match(text or ""))
