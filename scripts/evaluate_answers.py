"""Evaluate the FINAL answers of the full pipeline (retrieve -> generate -> verify).

Runs every question in outputs/test_cases/retrieval_eval.json through NyayaAI,
prints summary metrics, and saves every full answer to outputs/answer_eval/
so a human can read them.

This calls the OpenAI API (costs money). Try a few questions first:
    python -m scripts.evaluate_answers --limit 2
Then the full run:
    python -m scripts.evaluate_answers
"""

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app import config

EVAL_FILE = Path("outputs/test_cases/retrieval_eval.json")
RESULTS_DIR = Path("outputs/answer_eval")

# Used ONLY for a rough cost estimate. Prices change: check
# https://developers.openai.com/api/docs/models (gpt-6.1-terra, checked 2026-11-05).
PRICE_PER_MILLION_INPUT = 1.00
PRICE_PER_MILLION_OUTPUT = 5.00


def score_answer(case: dict, response: dict, citation_of: dict[str, str]) -> dict:
    """Turn one case + one assistant response into pass/fail checks.

    citation_of maps "patents_act_1970:53" -> "Section 53, The Patents Act, 1970",
    so we can tell whether an expected section was among the sources given to the model.
    """
    verified = [c for c in response["citations"] if c["verified"]]
    rejected = [c for c in response["citations"] if not c["verified"]]
    abstained = response["confidence"] == "insufficient"

    if case["set"] == "out_of_scope":
        # Correct behaviour: admit it cannot answer, and cite no law.
        passed = abstained and not verified
        return {"passed": passed, "verified": len(verified), "rejected": len(rejected), "abstained": abstained}

    retrieved_correct = any(citation_of[s] in response["sources_considered"] for s in case["expected"])
    grounded = not abstained and len(verified) > 0
    correct_law = any(c["section_id"] in case["expected"] for c in verified)
    return {
        "retrieved_correct": retrieved_correct,  # was a right section GIVEN to the model?
        "grounded": grounded,
        "correct_law": correct_law,  # did the model CITE a right section (verified)?
        "passed": grounded and correct_law,
        "verified": len(verified),
        "rejected": len(rejected),
        "abstained": abstained,
        # Abstaining is wrong when the right section was in front of the model.
        "abstained_despite_source": abstained and retrieved_correct,
    }


def summarise(records: list[dict]) -> list[str]:
    """Build the summary lines printed at the end."""
    lines = []
    for set_name in dict.fromkeys(r["set"] for r in records):  # every set, in the order run
        subset = [r for r in records if r["set"] == set_name]
        if not subset:
            continue
        n = len(subset)
        if set_name == "out_of_scope":
            ok = sum(r["score"]["passed"] for r in subset)
            lines.append(f"[{set_name}] correctly said 'insufficient': {ok}/{n}")
        else:
            retrieved = sum(r["score"]["retrieved_correct"] for r in subset)
            grounded = sum(r["score"]["grounded"] for r in subset)
            correct = sum(r["score"]["correct_law"] for r in subset)
            wrong_abstain = sum(r["score"]["abstained_despite_source"] for r in subset)
            lines.append(
                f"[{set_name}] correct law retrieved: {retrieved}/{n}   grounded: {grounded}/{n}   "
                f"correct law cited: {correct}/{n}   abstained despite source: {wrong_abstain}"
            )

    verified = sum(r["score"]["verified"] for r in records)
    rejected = sum(r["score"]["rejected"] for r in records)
    total = verified + rejected
    rate = f"{verified / total:.0%}" if total else "n/a"
    lines.append(f"citations: {verified} verified, {rejected} rejected (verification rate {rate})")

    confidences = {}
    for r in records:
        confidences[r["response"]["confidence"]] = confidences.get(r["response"]["confidence"], 0) + 1
    lines.append(f"confidence: {confidences}")

    latencies = sorted(r["seconds"] for r in records)
    tokens_in = sum(r["response"]["input_tokens"] for r in records)
    tokens_out = sum(r["response"]["output_tokens"] for r in records)
    cost = tokens_in / 1e6 * PRICE_PER_MILLION_INPUT + tokens_out / 1e6 * PRICE_PER_MILLION_OUTPUT
    lines.append(f"latency: median {latencies[len(latencies) // 2]:.1f}s, max {latencies[-1]:.1f}s")
    lines.append(
        f"tokens: {tokens_in:,} in, {tokens_out:,} out  ->  estimated cost ${cost:.3f} "
        f"(${cost / len(records):.4f} per question)"
    )
    return lines


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evaluate NyayaAI's final answers.")
    parser.add_argument("--limit", type=int, help="only run the first N questions (to test cheaply)")
    parser.add_argument("--cases", action="append", default=[],
                        help="extra question file(s), e.g. outputs/test_cases/criminal_eval.json")
    parser.add_argument("--only-set", action="append", default=[],
                        help="run only these sets, e.g. --only-set criminal --only-set criminal_owner")
    parser.add_argument("--context-sections", type=int, default=config.ANSWER_CONTEXT_SECTIONS,
                        help=f"sections given to the model per question (default {config.ANSWER_CONTEXT_SECTIONS})")
    args = parser.parse_args()

    if not config.OPENAI_API_KEY:
        print("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")
        return

    from scripts.search import build_assistant  # slow import: loads the search models

    cases = []
    for path in [EVAL_FILE, *map(Path, args.cases)]:
        cases += json.loads(path.read_text(encoding="utf-8"))["cases"]
    if args.only_set:
        cases = [c for c in cases if c["set"] in args.only_set]
    if args.limit:
        cases = cases[: args.limit]
    assistant = build_assistant()
    assistant.context_sections = args.context_sections
    from app.services.retriever import load_sections
    from scripts.search import PROCESSED_DIR, SOURCES_FILE

    source_ids = [s["id"] for s in json.loads(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]]
    citation_of = {f"{s.source_id}:{s.section}": s.citation for s in load_sections(PROCESSED_DIR, source_ids)}
    print(f"model: {config.OPENAI_MODEL}   context sections: {args.context_sections}   "
          f"query rewrite: {config.QUERY_REWRITE_MODEL if config.USE_QUERY_REWRITE else 'off'}\n")

    records = []
    for number, case in enumerate(cases, start=1):
        start = time.perf_counter()
        try:
            response = asdict(assistant.ask(case["question"]))
        except Exception as error:  # keep going; one failure should not stop the whole run
            print(f"{number:2}. ERROR    [{case['set']}] {case['question']}\n      {type(error).__name__}: {error}")
            continue
        seconds = time.perf_counter() - start

        score = score_answer(case, response, citation_of)
        records.append({"set": case["set"], "expected": case["expected"], "seconds": round(seconds, 1),
                        "also_check": case.get("also_check"),
                        "score": score, "response": response})

        status = "PASS" if score["passed"] else "FAIL"
        print(f"{number:2}. {status}  [{case['set']}] {case['question']}")
        print(f"      confidence={response['confidence']}  citations: {score['verified']} verified, "
              f"{score['rejected']} rejected  ({seconds:.1f}s)")

    if not records:
        return

    print("\nSUMMARY")
    for line in summarise(records):
        print("  " + line)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    areas = "+".join(config.ENABLED_DOMAINS)
    output = RESULTS_DIR / (f"{datetime.now():%Y-%m-%d_%H%M%S}_{config.OPENAI_MODEL}"
                            f"_ctx{args.context_sections}_{areas}.json")
    output.write_text(json.dumps({"model": config.OPENAI_MODEL, "context_sections": args.context_sections,
                                  "areas_of_law": config.ENABLED_DOMAINS, "results": records},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFull answers saved to {output} - please read some of them.")


if __name__ == "__main__":
    main()
