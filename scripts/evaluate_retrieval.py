"""Measure how well each search method finds the correct sections.

For each question in outputs/test_cases/retrieval_eval.json, check whether an
expected section appears in the top K results. Prints a score table for every
method (bm25, embeddings, hybrid), then per-question details for hybrid.

Run from the project root:
    python -m scripts.evaluate_retrieval
"""

import json
from pathlib import Path

from scripts.search import build_retrievers

EVAL_FILE = Path("outputs/test_cases/retrieval_eval.json")
TOP_K = 5
DETAIL_METHOD = "hybrid"


def section_key(section) -> str:
    """The same "source_id:section" format used in the eval file."""
    return f"{section.source_id}:{section.section}"


def rank_of_expected(retriever, case) -> tuple[int | None, list[str]]:
    """Rank (1 = best) of the first expected section in the top K, or None; plus what was found."""
    found = [section_key(r.section) for r in retriever.search(case["question"], top_k=TOP_K)]
    rank = next((i for i, key in enumerate(found, start=1) if key in case["expected"]), None)
    return rank, found


def main() -> None:
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))["cases"]
    retrievers = build_retrievers()
    sets = list(dict.fromkeys(case["set"] for case in cases))  # e.g. ["tuning", "held_out"]

    # 1. Score table: one row per method.
    print(f"\nCorrect section in the top {TOP_K}:\n")
    print(f"{'method':<12}" + "".join(f"{name:>12}" for name in sets))
    for method, retriever in retrievers.items():
        row = f"{method:<12}"
        for name in sets:
            subset = [c for c in cases if c["set"] == name]
            passed = sum(rank_of_expected(retriever, c)[0] is not None for c in subset)
            row += f"{f'{passed}/{len(subset)}':>12}"
        print(row)

    # 2. Details for one method.
    print(f"\nDetails for {DETAIL_METHOD}:\n")
    for case in cases:
        rank, found = rank_of_expected(retrievers[DETAIL_METHOD], case)
        label = f"[{case['set']}]"
        if rank is not None:
            print(f"PASS (rank {rank}) {label:11} {case['question']}")
        else:
            print(f"FAIL          {label:11} {case['question']}")
            print(f"    expected: {case['expected']}")
            print(f"    got:      {found}")


if __name__ == "__main__":
    main()
