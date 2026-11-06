"""Compare two answer-evaluation runs question by question (no API calls).

Usage:
    python -m scripts.compare_answer_runs <run A>.json <run B>.json
Works with plain results files and with *_judged.json files (adds judge columns).
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from scripts.evaluate_answers import PRICE_PER_MILLION_INPUT, PRICE_PER_MILLION_OUTPUT


def cost(response: dict) -> float:
    return (response["input_tokens"] / 1e6 * PRICE_PER_MILLION_INPUT
            + response["output_tokens"] / 1e6 * PRICE_PER_MILLION_OUTPUT)


def run_summary(data: dict) -> dict:
    records = data["results"]
    in_scope = [r for r in records if r["set"] != "out_of_scope"]
    out_scope = [r for r in records if r["set"] == "out_of_scope"]
    summary = {
        "correct law retrieved": f"{sum(r['score']['retrieved_correct'] for r in in_scope)}/{len(in_scope)}",
        "correct law cited": f"{sum(r['score']['correct_law'] for r in in_scope)}/{len(in_scope)}",
        "  tuning": "{}/{}".format(sum(r["score"]["correct_law"] for r in in_scope if r["set"] == "tuning"),
                                   sum(r["set"] == "tuning" for r in in_scope)),
        "  held_out": "{}/{}".format(sum(r["score"]["correct_law"] for r in in_scope if r["set"] == "held_out"),
                                     sum(r["set"] == "held_out" for r in in_scope)),
        "  fresh": "{}/{}".format(sum(r["score"]["correct_law"] for r in in_scope if r["set"] == "fresh"),
                                  sum(r["set"] == "fresh" for r in in_scope)),
        "  fresh2": "{}/{}".format(sum(r["score"]["correct_law"] for r in in_scope if r["set"] == "fresh2"),
                                   sum(r["set"] == "fresh2" for r in in_scope)),
        "abstained (in scope)": sum(r["score"]["abstained"] for r in in_scope),
        "abstained despite source": sum(r["score"]["abstained_despite_source"] for r in in_scope),
        "out-of-scope refused": f"{sum(r['score']['passed'] for r in out_scope)}/{len(out_scope)}",
    }
    verified = sum(r["score"]["verified"] for r in records)
    rejected = sum(r["score"]["rejected"] for r in records)
    summary["citations verified"] = f"{verified}/{verified + rejected}"

    if any("judgement" in r for r in records):
        verdicts = Counter(c["verdict"] for r in records if r.get("judgement") for c in r["judgement"]["citations"])
        judged_total = sum(verdicts.values())
        summary["judge: citations supported"] = f"{verdicts['supported']}/{judged_total}"
        summary["judge: partially supported"] = verdicts["partially_supported"]
        summary["judge: out of context"] = verdicts["out_of_context"]
        summary["judge: not supported"] = verdicts["not_supported"]
        judged = [r["judgement"] for r in records if r.get("judgement")]
        overall = Counter(j["overall"] for j in judged)
        summary["judge: answers accurate"] = f"{overall['accurate']}/{len(judged)}"
        summary["judge: significant issues"] = overall["significant_issues"]
        summary["judge: unsupported claims"] = sum(len(j["unsupported_claims"]) for j in judged)
        summary["judge: combination errors"] = sum(len(j["combination_errors"]) for j in judged)

    seconds = [r["seconds"] for r in records]
    costs = [cost(r["response"]) for r in records]
    summary["median latency (s)"] = round(statistics.median(seconds), 1)
    summary["max latency (s)"] = max(seconds)
    summary["tokens in per question"] = round(statistics.mean(r["response"]["input_tokens"] for r in records))
    summary["cost per question ($)"] = round(statistics.mean(costs), 4)
    summary["total cost ($)"] = round(sum(costs), 3)
    return summary


def short(record: dict) -> str:
    s = record["score"]
    if record["set"] == "out_of_scope":
        return "refused" if s["passed"] else "ANSWERED"
    retrieved = "R" if s["retrieved_correct"] else "-"
    cited = "C" if s["correct_law"] else "-"
    status = "abstain" if s["abstained"] else record["response"]["confidence"]
    judge = ""
    if record.get("judgement"):
        judge = {"accurate": " ok", "minor_issues": " minor", "significant_issues": " SIGNIF"}[record["judgement"]["overall"]]
    return f"{retrieved}{cited} {status}{judge}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    args = parser.parse_args()
    a = json.loads(args.run_a.read_text(encoding="utf-8"))
    b = json.loads(args.run_b.read_text(encoding="utf-8"))
    label_a = f"A (ctx {a.get('context_sections', '?')})"
    label_b = f"B (ctx {b.get('context_sections', '?')})"

    print(f"\n{'metric':<30}{label_a:>16}{label_b:>16}")
    sa, sb = run_summary(a), run_summary(b)
    for key in sa:
        print(f"{key:<30}{str(sa[key]):>16}{str(sb.get(key, '')):>16}")

    print("\nPer question (R = correct law retrieved, C = correct law cited and verified):\n")
    by_question_b = {r["response"]["question"]: r for r in b["results"]}
    for ra in a["results"]:
        question = ra["response"]["question"]
        rb = by_question_b.get(question)
        sa_, sb_ = short(ra), short(rb) if rb else "missing"
        marker = "  " if sa_ == sb_ else "* "
        print(f"{marker}[{ra['set'][:8]:8}] {sa_:<22} {sb_:<22} {question[:58]}")


if __name__ == "__main__":
    main()
