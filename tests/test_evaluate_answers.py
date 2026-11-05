"""Tests for the scoring logic in scripts/evaluate_answers.py (no API calls)."""

from scripts.evaluate_answers import score_answer, summarise


def citation(section_id: str, verified: bool) -> dict:
    return {"section_id": section_id, "verified": verified}


def response(confidence: str, citations: list[dict]) -> dict:
    return {"confidence": confidence, "citations": citations, "input_tokens": 1000, "output_tokens": 100}


IN_SCOPE = {"set": "held_out", "expected": ["patents_act_1970:53"]}
OUT_OF_SCOPE = {"set": "out_of_scope", "expected": []}


def test_pass_when_expected_section_is_cited_and_verified():
    score = score_answer(IN_SCOPE, response("high", [citation("patents_act_1970:53", True)]))

    assert score == {"grounded": True, "correct_law": True, "passed": True, "verified": 1, "rejected": 0}


def test_expected_section_cited_but_rejected_does_not_count():
    score = score_answer(IN_SCOPE, response("high", [citation("patents_act_1970:53", False)]))

    assert not score["correct_law"]
    assert not score["passed"]
    assert score["rejected"] == 1


def test_grounded_in_the_wrong_section_fails():
    score = score_answer(IN_SCOPE, response("high", [citation("patents_act_1970:48", True)]))

    assert score["grounded"] and not score["correct_law"] and not score["passed"]


def test_out_of_scope_passes_only_when_insufficient_without_citations():
    assert score_answer(OUT_OF_SCOPE, response("insufficient", []))["passed"]
    assert not score_answer(OUT_OF_SCOPE, response("low", []))["passed"]
    assert not score_answer(OUT_OF_SCOPE, response("insufficient", [citation("x:1", True)]))["passed"]


def test_summary_counts_and_verification_rate():
    records = [
        {"set": "held_out", "seconds": 4.0, "response": response("high", []),
         "score": {"grounded": True, "correct_law": True, "passed": True, "verified": 3, "rejected": 1}},
        {"set": "out_of_scope", "seconds": 2.0, "response": response("insufficient", []),
         "score": {"passed": True, "verified": 0, "rejected": 0}},
    ]

    lines = summarise(records)

    assert "[held_out] grounded: 1/1   correct law cited: 1/1" in lines
    assert "[out_of_scope] correctly said 'insufficient': 1/1" in lines
    assert "citations: 3 verified, 1 rejected (verification rate 75%)" in lines
