"""Tests for the scoring logic in scripts/evaluate_answers.py (no API calls)."""

from scripts.evaluate_answers import score_answer, summarise

CITATION_OF = {
    "patents_act_1970:53": "Section 53, The Patents Act, 1970",
    "patents_act_1970:48": "Section 48, The Patents Act, 1970",
}
IN_SCOPE = {"set": "held_out", "expected": ["patents_act_1970:53"]}
OUT_OF_SCOPE = {"set": "out_of_scope", "expected": []}


def citation(section_id: str, verified: bool) -> dict:
    return {"section_id": section_id, "verified": verified}


def response(confidence: str, citations: list[dict], sources=("Section 53, The Patents Act, 1970",)) -> dict:
    return {"confidence": confidence, "citations": citations, "sources_considered": list(sources),
            "input_tokens": 1000, "output_tokens": 100}


def score(case, resp):
    return score_answer(case, resp, CITATION_OF)


def test_pass_when_expected_section_is_cited_and_verified():
    result = score(IN_SCOPE, response("high", [citation("patents_act_1970:53", True)]))

    assert result["passed"] and result["retrieved_correct"] and result["correct_law"]
    assert not result["abstained_despite_source"]


def test_expected_section_cited_but_rejected_does_not_count():
    result = score(IN_SCOPE, response("high", [citation("patents_act_1970:53", False)]))

    assert not result["correct_law"] and not result["passed"]
    assert result["rejected"] == 1


def test_grounded_in_the_wrong_section_fails():
    result = score(IN_SCOPE, response("high", [citation("patents_act_1970:48", True)]))

    assert result["grounded"] and not result["correct_law"] and not result["passed"]


def test_abstaining_when_right_section_was_given_is_flagged():
    result = score(IN_SCOPE, response("insufficient", []))

    assert result["abstained_despite_source"]


def test_abstaining_when_right_section_was_not_retrieved_is_not_flagged():
    result = score(IN_SCOPE, response("insufficient", [], sources=["Section 48, The Patents Act, 1970"]))

    assert not result["retrieved_correct"]
    assert not result["abstained_despite_source"]


def test_out_of_scope_passes_only_when_insufficient_without_citations():
    assert score(OUT_OF_SCOPE, response("insufficient", []))["passed"]
    assert not score(OUT_OF_SCOPE, response("low", []))["passed"]
    assert not score(OUT_OF_SCOPE, response("insufficient", [citation("x:1", True)]))["passed"]


def test_summary_counts_and_verification_rate():
    records = [
        {"set": "held_out", "seconds": 4.0, "response": response("high", []),
         "score": {"retrieved_correct": True, "grounded": True, "correct_law": True, "passed": True,
                   "verified": 3, "rejected": 1, "abstained": False, "abstained_despite_source": False}},
        {"set": "out_of_scope", "seconds": 2.0, "response": response("insufficient", []),
         "score": {"passed": True, "verified": 0, "rejected": 0, "abstained": True}},
    ]

    lines = summarise(records)

    assert ("[held_out] correct law retrieved: 1/1   grounded: 1/1   correct law cited: 1/1   "
            "abstained despite source: 0") in lines
    assert "[out_of_scope] correctly said 'insufficient': 1/1" in lines
    assert "citations: 3 verified, 1 rejected (verification rate 75%)" in lines


def test_scenario_questions_are_recorded_but_not_scored():
    from scripts.evaluate_answers import score_answer, summarise

    case = {"question": "q", "expected": [], "set": "scenario"}
    response = {"citations": [{"verified": True, "section_id": "bns_2023:78"}], "confidence": "high",
                "sources_considered": []}
    score = score_answer(case, response, {})
    assert score["passed"] is None and score["verified"] == 1

    record = {"set": "scenario", "score": score, "seconds": 1.0,
              "response": {"confidence": "high", "input_tokens": 1, "output_tokens": 1}}
    assert any("not scored" in line for line in summarise([record]))
