"""The filing guides are fixed, hand-checked data: test every quote, link and source. No API calls."""

import json
import re
from pathlib import Path

from app.filing_guides import guide_for, load_filing_guides
from app.services.citation_verifier import normalise_for_matching
from app.services.drafter import DOCUMENT_TYPES, GUIDES

GUIDES_DATA = load_filing_guides()
PROCESSED = Path("data/processed")
OFFICIAL = re.compile(r"^https://(?:www\.)?[a-z0-9.-]+\.(?:gov\.in|nic\.in)(?:/|$)")


def section_text(section_id: str) -> str:
    source_id, number = section_id.split(":")
    sections = json.loads((PROCESSED / f"{source_id}_sections.json").read_text(encoding="utf-8"))
    return next(s["text"] for s in sections if s["section"] == number)


def all_steps():
    return [step for guide in GUIDES_DATA["guides"] for step in guide["steps"]]


def test_every_law_quote_is_in_the_act_text():
    quotes = [step["law"] for step in all_steps() if "law" in step]
    assert quotes
    for law in quotes:
        assert normalise_for_matching(law["quote"]) in normalise_for_matching(section_text(law["section_id"])), law


def test_every_link_is_an_official_government_site_with_a_checked_source():
    for step in all_steps():
        if "link" in step:
            assert OFFICIAL.match(step["link"]), step["link"]
            assert step.get("checked_source"), step["heading"]
    assert GUIDES_DATA["checked_on"] and GUIDES_DATA["legal_aid"]["checked_source"]


def test_never_claims_nyayaai_files_anything():
    text = json.dumps(GUIDES_DATA["guides"]).lower()
    for phrase in ["nyayaai has filed", "nyayaai has submitted", "we have filed", "we will file", "has been submitted"]:
        assert phrase not in text


def test_no_fees_or_commission_limits():
    # Fees and value limits come from Rules NyayaAI does not have: no rupee amounts anywhere in the guides.
    assert not re.search(r"(₹|rs\.?\s*\d|rupees|lakh|crore)", json.dumps(GUIDES_DATA["guides"], ensure_ascii=False),
                         re.IGNORECASE)


def test_every_guide_the_drafter_can_choose_exists():
    for guide_id in [g for g in GUIDES if g != "none"] + [g for _, g in DOCUMENT_TYPES.values() if g]:
        assert guide_for(GUIDES_DATA, guide_id), guide_id
    assert guide_for(GUIDES_DATA, "none") is None
