"""Measure how well retrieval finds the correct sections.

For each question in outputs/test_cases/retrieval_eval.json, check whether an
expected section appears in the top K search results. Scores are reported
separately for the "tuning" and "held_out" sets.

Run from the project root:
    python -m scripts.evaluate_retrieval
"""

import json
from collections import Counter
from pathlib import Path

from scripts.search import build_retriever

EVAL_FILE = Path("outputs/test_cases/retrieval_eval.json")
TOP_K = 5


def section_key(section) -> str:
    """The same "source_id:section" format used in the eval file."""
    return f"{section.source_id}:{section.section}"


def main() -> None:
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))["cases"]
    retriever = build_retriever()
    passed = Counter()  # passes per set
    total = Counter()  # questions per set

    for case in cases:
        results = retriever.search(case["question"], top_k=TOP_K)
        found_keys = [section_key(r.section) for r in results]

        # Rank (1 = best) of the first expected section found, or None.
        rank = next(
            (position for position, key in enumerate(found_keys, start=1) if key in case["expected"]),
            None,
        )

        total[case["set"]] += 1
        label = f"[{case['set']}]"
        if rank is not None:
            passed[case["set"]] += 1
            print(f"PASS (rank {rank}) {label:11} {case['question']}")
        else:
            print(f"FAIL          {label:11} {case['question']}")
            print(f"    expected: {case['expected']}")
            print(f"    got:      {found_keys}")

    print()
    for name in total:
        print(f"Score [{name}]: {passed[name]}/{total[name]} questions had a correct section in the top {TOP_K}")


if __name__ == "__main__":
    main()
