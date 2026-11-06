"""Turn saved evaluation results into a readable, UNEDITED record of NyayaAI's answers.

Reads a results file written by scripts.evaluate_answers (outputs/answer_eval/*.json) and writes
outputs/raw_outputs/<same name>.md: for every question, NyayaAI's answer exactly as produced,
its confidence, safety notes, next steps, every citation (verified or not), the sections it was
given, and the automatic score. Nothing is rewritten, shortened or filtered.

    python -m scripts.export_raw_outputs outputs/answer_eval/<results>.json
"""

import json
import sys
from pathlib import Path

OUT_DIR = Path("outputs/raw_outputs")


def to_markdown(results: dict, source_name: str) -> str:
    lines = [
        f"# NyayaAI raw outputs: {source_name}",
        "",
        f"Model: `{results.get('model')}`, context sections: {results.get('context_sections')}, "
        f"areas of law: {', '.join(results.get('areas_of_law', []))}.",
        "Answers are exactly as NyayaAI produced them (not edited). Citation IDs like "
        "`[bns_2023:78]` mean Section 78 of that Act. The automatic score only checks whether a correct "
        "section was cited; it does not judge the whole answer.",
        "",
    ]
    for number, record in enumerate(results["results"], start=1):
        r, score = record["response"], record["score"]
        lines += [
            "---",
            "",
            f"## {number}. [{record['set']}] {r['question']}",
            "",
            f"**Confidence:** {r['confidence']} (model said: {r['model_confidence']})  ",
            f"**Expected sections:** {', '.join(record['expected']) or ('not scored' if record['set'] == 'scenario' else 'none (out of scope)')}  ",
            f"**Automatic result:** {'not scored (real-life scenario)' if score['passed'] is None else ('PASS' if score['passed'] else 'FAIL')}  ",
            f"**Time:** {record['seconds']} s",
            "",
            "### Answer",
            "",
            r["answer"],
            "",
        ]
        if r.get("safety_notes"):
            lines += ["### Safety notes (added by code)", ""]
            lines += [f"- [{n['kind']}] {n['text']} (source: {n['source']})" for n in r["safety_notes"]]
            lines.append("")
        if r["next_steps"]:
            lines += ["### Next steps", ""] + [f"- {step}" for step in r["next_steps"]] + [""]
        if r["citations"]:
            lines += ["### Citations", ""]
            for c in r["citations"]:
                status = "VERIFIED" if c["verified"] else f"NOT VERIFIED ({c['reason']})"
                where = c["citation"] or c["section_id"]
                lines.append(f"- **{status}** {where}: \"{c['quote']}\"  \n  supports: {c['supports']}")
            lines.append("")
        if record.get("also_check"):
            lines += [f"*Checked by hand for:* {record['also_check']}", ""]
        lines += ["<details><summary>Sections given to the model</summary>", "",
                  "; ".join(r["sources_considered"]), "", "</details>", ""]
    return "\n".join(lines)


def main() -> None:
    source = Path(sys.argv[1])
    results = json.loads(source.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{source.stem}.md"
    out.write_text(to_markdown(results, source.stem), encoding="utf-8")
    print(f"{len(results['results'])} answers written to {out}")


if __name__ == "__main__":
    main()
