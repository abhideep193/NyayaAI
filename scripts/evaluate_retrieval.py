"""Measure how well each search method finds the correct sections, and how fast.

For each question in outputs/test_cases/retrieval_eval.json, check whether an
expected section appears in the top 5 and top 15 results, and time each search.
Prints a table for every method, then per-question details for the best method.

Run from the project root:
    python -m scripts.evaluate_retrieval
"""

import json
import statistics
import time
from pathlib import Path

from scripts.search import build_retrievers

EVAL_FILE = Path("outputs/test_cases/retrieval_eval.json")
CUTOFFS = [5, 15]


def section_key(section) -> str:
    """The same "source_id:section" format used in the eval file."""
    return f"{section.source_id}:{section.section}"


def run_method(retriever, cases: list[dict]) -> tuple[list[dict], list[float]]:
    """Search every question once (top 15). Return per-question results and latencies in seconds."""
    retriever.search("warm-up question", top_k=max(CUTOFFS))  # first call can be slow; not timed

    outcomes, latencies = [], []
    for case in cases:
        start = time.perf_counter()
        results = retriever.search(case["question"], top_k=max(CUTOFFS))
        latencies.append(time.perf_counter() - start)

        found = [section_key(r.section) for r in results]
        rank = next((i for i, key in enumerate(found, start=1) if key in case["expected"]), None)
        outcomes.append({"case": case, "rank": rank, "found": found})
    return outcomes, latencies


def count_passes(outcomes: list[dict], set_name: str, cutoff: int) -> str:
    subset = [o for o in outcomes if o["case"]["set"] == set_name]
    passed = sum(o["rank"] is not None and o["rank"] <= cutoff for o in subset)
    return f"{passed}/{len(subset)}"


def main() -> None:
    cases = json.loads(EVAL_FILE.read_text(encoding="utf-8"))["cases"]
    cases = [c for c in cases if c["expected"]]  # out-of-scope questions have no right section
    retrievers = build_retrievers()

    sets = list(dict.fromkeys(c["set"] for c in cases))  # e.g. tuning, held_out, fresh
    columns = [f"{s}@{k}" for s in sets for k in CUTOFFS] + ["median latency"]
    print("\n" + f"{'method':<12}" + "".join(f"{c:>13}" for c in columns))

    all_outcomes = {}
    for method, retriever in retrievers.items():
        outcomes, latencies = run_method(retriever, cases)
        all_outcomes[method] = outcomes
        row = f"{method:<12}"
        for set_name in sets:
            for cutoff in CUTOFFS:
                row += f"{count_passes(outcomes, set_name, cutoff):>13}"
        row += f"{statistics.median(latencies) * 1000:>10.0f} ms"
        print(row)

    detail_method = list(retrievers)[-1]  # the most advanced method that was built
    print(f"\nDetails for {detail_method} (rank of first correct section; FAIL = not in top {max(CUTOFFS)}):\n")
    for o in all_outcomes[detail_method]:
        label = f"[{o['case']['set']}]"
        status = f"rank {o['rank']:>2}" if o["rank"] else "FAIL   "
        print(f"{status}  {label:11} {o['case']['question']}")


if __name__ == "__main__":
    main()
