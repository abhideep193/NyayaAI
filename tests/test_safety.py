"""Tests for app/safety.py (helplines and the old-criminal-law notice, added by code)."""

from datetime import date
from pathlib import Path

import pytest

from app.safety import helplines_for, load_safety, mentions_date_before, safety_notes

SAFETY = load_safety(Path(__file__).parent.parent / "data/legal_sources/safety.json")
CUTOFF = date(2024, 7, 1)
DOMAIN_OF = {"bns_2023": "criminal", "pocso_act_2012": "criminal", "it_act_2000": "criminal",
             "copyright_act_1957": "ipr"}


@pytest.mark.parametrize("question, expected", [
    ("Someone cheated me in March 2023 and I filed an FIR", True),
    ("It happened on 15/03/2024 near my house", True),
    ("This happened in June 2024", True),
    ("This happened in July 2024", False),
    ("This happened in 2025", False),
    ("Is this an offence under the Dowry Prohibition Act, 1961?", False),  # year is part of a law's name
    ("What does the Bharatiya Nyaya Sanhita 2023 say about theft?", False),
    ("My uncle hit me yesterday", False),
])
def test_dates_before_the_new_criminal_laws(question, expected):
    assert mentions_date_before(question, CUTOFF) is expected


def test_old_law_notice_only_for_criminal_answers():
    question = "Someone cheated me in March 2023"
    criminal = safety_notes(question, ["bns_2023:318"], DOMAIN_OF, SAFETY)
    ipr = safety_notes(question, ["copyright_act_1957:51"], DOMAIN_OF, SAFETY)
    assert criminal[0].kind == "old_law" and "1 July 2024" in criminal[0].text
    assert "S.O. 850(E)" in criminal[0].source and "S.O. 848(E)" in criminal[0].source
    assert ipr == []


def test_child_question_gets_child_helpline_and_emergency():
    texts = [n.text for n in helplines_for(["pocso_act_2012:19"], SAFETY)]
    assert any("1098" in t for t in texts) and any("112" in t for t in texts)
    assert not any("1930" in t for t in texts)


def test_cyber_and_sexual_offence_sections_choose_their_helplines():
    assert any("1930" in n.text for n in helplines_for(["bns_2023:308"], SAFETY))  # extortion
    assert any("181" in n.text for n in helplines_for(["bns_2023:78"], SAFETY))  # stalking
    assert not any("181" in n.text for n in helplines_for(["bns_2023:248"], SAFETY))  # false charge


def test_no_helplines_for_ipr_or_unverified_answers():
    assert helplines_for(["copyright_act_1957:51"], SAFETY) == []
    assert helplines_for([], SAFETY) == []


def test_every_helpline_has_an_official_source():
    for helpline in SAFETY["helplines"]:
        assert ".gov.in" in helpline["source"]


# Cases found in the hand review of 2026-11-06: safety notes must not depend only on what the model cited.

def test_old_law_notice_shown_when_criminal_law_was_searched_but_nothing_cited():
    notes = safety_notes("Someone cheated me in March 2023. New BNS or old IPC?", [], DOMAIN_OF, SAFETY,
                         retrieved_section_ids=["bns_2023:318", "bns_2023:1"])
    assert [n.kind for n in notes][0] == "old_law"


def test_otp_fraud_gets_cyber_helpline_even_if_a_different_section_is_cited():
    notes = safety_notes("Someone pretending to be my bank got my OTP and took ₹45,000", ["bns_2023:314"],
                         DOMAIN_OF, SAFETY, retrieved_section_ids=["bns_2023:314", "bns_2023:316"])
    assert any("1930" in n.text for n in notes)


def test_keywords_alone_do_not_add_criminal_notes_to_ipr_answers():
    notes = safety_notes("Someone hacked my YouTube channel in 2023 and reuploaded my videos",
                         ["copyright_act_1957:51"], DOMAIN_OF, SAFETY, retrieved_section_ids=["copyright_act_1957:51"])
    assert notes == []


PROPERTY_DOMAIN_OF = {**DOMAIN_OF, "transfer_of_property_act_1882": "property", "copyright_act_1957": "ipr"}


def test_state_law_note_whenever_property_law_was_searched():
    # cited
    notes = safety_notes("Can my landlord evict me?", ["transfer_of_property_act_1882:106"], PROPERTY_DOMAIN_OF, SAFETY)
    assert [n.kind for n in notes] == ["state_law"]
    # only retrieved, nothing cited (e.g. the model declined): the note must still appear
    notes = safety_notes("Can my landlord evict me?", [], PROPERTY_DOMAIN_OF, SAFETY, ["transfer_of_property_act_1882:111"])
    assert [n.kind for n in notes] == ["state_law"]


def test_no_state_law_note_for_other_areas():
    notes = safety_notes("Someone copied my song", ["copyright_act_1957:51"], PROPERTY_DOMAIN_OF, SAFETY,
                         ["copyright_act_1957:51"])
    assert not [n for n in notes if n.kind == "state_law"]
