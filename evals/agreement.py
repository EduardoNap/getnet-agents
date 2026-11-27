"""How often the judge agrees with a person.

    python -m evals.agreement --sample 40 --report evals/reports/answers.json   # adds 40 answers to label
    python -m evals.agreement                                                    # judges the labelled answers and compares

To label: open human_labels.jsonl, read each answer against its reference and its evidence, and
replace each null with true or false. The judge's verdicts are not in the file, so they cannot
bias the labels. Each row carries the answer it is about, so the comparison grades exactly the
text the person read, whatever reports have been written since. It costs one judge call per row.

A model does not grade answers it wrote: rows answered by the judge's own model are left out.
"""
import argparse
import json
import random
from pathlib import Path

HERE = Path(__file__).parent
LABELS = HERE / "human_labels.jsonl"
GRADES = ["correct", "grounded", "complete", "useful"]


def cohen_kappa(first: list[bool], second: list[bool]) -> float | None:
    """Agreement beyond what two raters would reach by chance. 1 is perfect, 0 is chance.

    None when both raters gave the same label to every answer: there is nothing to measure.
    """
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / n
    yes_first, yes_second = sum(first) / n, sum(second) / n
    expected = yes_first * yes_second + (1 - yes_first) * (1 - yes_second)
    return None if expected == 1 else round((observed - expected) / (1 - expected), 3)


def compare(judged: dict, labels: list[dict]) -> dict:
    report = {}
    for grade in GRADES:
        pairs = [(label[grade], judged[(label["id"], label["repeat"])][grade]) for label in labels if label.get(grade) is not None]
        if pairs:
            human, model = zip(*pairs)
            report[grade] = {
                "labelled": len(pairs),
                "agreement": round(sum(h == m for h, m in pairs) / len(pairs), 3),
                "kappa": cohen_kappa(list(human), list(model)),
            }
    return report


def independent(labels: list[dict], judge_model: str) -> list[dict]:
    """The labelled rows this judge may grade: those its own model did not answer."""
    return [row for row in labels if row.get("grounded") is not None and row.get("answered_by") != judge_model]


def add_samples(labelled: list[dict], results: list[dict], cases: dict, count: int, answered_by: str) -> list[dict]:
    """The labels so far, plus up to `count` judged answers that have no label yet, chosen at random."""
    have = {(row["id"], row["repeat"]) for row in labelled}
    fresh = [r for r in results if "judge" in r and (r["id"], r["repeat"]) not in have]
    chosen = random.Random(7).sample(fresh, min(count, len(fresh)))
    return labelled + [
        {"id": r["id"], "repeat": r["repeat"], "message": r["message"], "reference": cases[r["id"]]["reference"],
         "answer": r["response"], "evidence": r["evidence"], "answered_by": answered_by,
         "correct": None, "grounded": None, "complete": None, "useful": None}
        for r in sorted(chosen, key=lambda r: (r["id"], r["repeat"]))
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, help="add this many answers to human_labels.jsonl for labelling")
    parser.add_argument("--report", default=str(HERE / "reports" / "answers.json"), help="the report to sample answers from")
    args = parser.parse_args()

    labels = [json.loads(line) for line in LABELS.read_text(encoding="utf-8").splitlines()] if LABELS.exists() else []
    if args.sample:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        cases = {c["id"]: c for c in map(json.loads, (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines())}
        rows = add_samples(labels, report["results"], cases, args.sample, report["meta"]["model"])
        LABELS.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
        print(f"{len(rows) - len(labels)} answers added to {LABELS}. Replace each null with true or false, then run this again.")
    elif not labels:
        print("No human labels yet. Run: python -m evals.agreement --sample 40")
    else:
        from evals import judge  # needs the API key

        done = independent(labels, judge.settings.judge_model)
        skipped = sum(row.get("grounded") is not None for row in labels) - len(done)
        judged = {
            (row["id"], row["repeat"]): judge.grade(row["message"], row["reference"], row["answer"], row["evidence"]).model_dump()
            for row in done
        }
        report = compare(judged, done)
        report["judge_model"], report["answers_by_the_judge_model_left_out"] = judge.settings.judge_model, skipped
        report["verdicts"] = [{"id": key[0], "repeat": key[1], **verdict} for key, verdict in judged.items()]
        (HERE / "reports" / "agreement.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({grade: report[grade] for grade in GRADES if grade in report}, indent=2))
        if skipped:
            print(f"{skipped} labelled answers left out: {judge.settings.judge_model} wrote them, so it does not grade them.")
