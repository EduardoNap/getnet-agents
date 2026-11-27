"""Retrieval evaluation on a held-out set. No API key needed.

    python -m evals.retrieval                    # writes evals/reports/retrieval.json and .md
    python -m evals.retrieval --min-recall 0.85  # also fails (exit 1) below the threshold: the CI gate

Each question in retrieval_set.jsonl has the page (or pages) that answers it, labelled by hand.
The questions are not the brief's examples, which were used to choose the keyword weight.
Questions are sent to the index as written. In the service the Knowledge Agent is told to search
in Portuguese, so English questions are also scored with a Portuguese rewrite (written by hand).

split=main found that error codes were ignored as keywords (see reports/retrieval_v1.md for the
numbers before the fix). split=confirm was written before the fix and looked at only after it.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from app.rag.retriever import CANDIDATES, KEYWORD_WEIGHT, VECTOR_WEIGHT, search
from evals import metrics

HERE = Path(__file__).parent
# (vector weight, keyword weight, search with the Portuguese rewrite of English questions)
MODES = {
    "vector only": (VECTOR_WEIGHT, 0.0, False),
    "keywords only": (0.0, KEYWORD_WEIGHT, False),
    "hybrid": (VECTOR_WEIGHT, KEYWORD_WEIGHT, False),
    "hybrid, English rewritten in Portuguese": (VECTOR_WEIGHT, KEYWORD_WEIGHT, True),
}
K = 6  # what the Knowledge Agent receives
COLUMNS = ["recall@1", "recall@3", "recall@6", "mrr", "ndcg@6", "context_precision@6"]


def score(ranked: list[str], gold: set[str]) -> dict:
    return {
        "recall@1": metrics.recall_at_k(ranked, gold, 1),
        "recall@3": metrics.recall_at_k(ranked, gold, 3),
        "recall@6": metrics.recall_at_k(ranked, gold, K),
        "mrr": metrics.reciprocal_rank(ranked, gold),
        "ndcg@6": metrics.ndcg_at_k(ranked, gold, K),
        "context_precision@6": metrics.context_precision(ranked, gold, K),
    }


def mean(rows: list[dict]) -> dict:
    return {column: round(sum(row[column] for row in rows) / len(rows), 3) for column in COLUMNS} | {"n": len(rows)}


def select(questions: list[dict], final: bool) -> list[dict]:
    """split=blind was written before the version 3 retrieval changes and is only scored in the final run."""
    return [question for question in questions if final or question["split"] != "blind"]


def run(final: bool = False) -> dict:
    questions = [json.loads(line) for line in (HERE / "retrieval_set.jsonl").read_text(encoding="utf-8").splitlines()]
    questions = select(questions, final)
    report = {"questions": len(questions), "k": K, "candidates": CANDIDATES, "modes": {}, "per_question": []}
    for mode, (vector_weight, keyword_weight, rewritten) in MODES.items():
        groups = defaultdict(list)
        for question in questions:
            query = question.get("pt", question["question"]) if rewritten else question["question"]
            ranked = [hit["source"] for hit in search(query, k=CANDIDATES, keyword_weight=keyword_weight, vector_weight=vector_weight)]
            scores = score(ranked, set(question["gold"]))
            for group in ("all", f"split={question['split']}", f"lang={question['lang']}", f"kind={question['kind']}"):
                groups[group].append(scores)
            report["per_question"].append(
                {"id": question["id"], "mode": mode, "question": question["question"], **scores, "top": metrics.pages(ranked)[:3]}
            )
        report["modes"][mode] = {group: mean(rows) for group, rows in sorted(groups.items())}
    return report


def as_markdown(report: dict) -> str:
    lines = [
        "# Retrieval evaluation",
        "",
        f"{report['questions']} questions that are not the brief's examples, each with its correct page labelled by hand. "
        f"Top {report['k']} chunks of {report['candidates']} candidates. Higher is better; 1.0 is perfect.",
        "",
        "| Group | Search | n | " + " | ".join(COLUMNS) + " |",
        "|---|---|---|" + "---|" * len(COLUMNS),
    ]
    for group in report["modes"]["hybrid"]:
        for mode in report["modes"]:
            row = report["modes"][mode][group]
            lines.append(f"| {group} | {mode} | {row['n']} | " + " | ".join(f"{row[c]:.3f}" for c in COLUMNS) + " |")
    production = "hybrid, English rewritten in Portuguese"
    misses = [q for q in report["per_question"] if q["mode"] == production and not q["recall@6"]]
    lines += ["", f"## Questions still missed in the top {report['k']} as the service searches ({len(misses)})", ""]
    lines += [f"- `{q['id']}` {q['question']}" for q in misses] or ["None."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-recall", type=float, help="fail when recall@6, searching as the service does, is below this")
    parser.add_argument("--final", action="store_true", help="also score the blind split; for the one run after the changes")
    parser.add_argument("--name", default="retrieval", help="report file name, without extension")
    args = parser.parse_args()

    report = run(args.final)
    (HERE / "reports").mkdir(exist_ok=True)
    (HERE / "reports" / f"{args.name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "reports" / f"{args.name}.md").write_text(as_markdown(report), encoding="utf-8")
    print(as_markdown(report))

    recall = report["modes"]["hybrid, English rewritten in Portuguese"]["all"]["recall@6"]
    if args.min_recall is not None and recall < args.min_recall:
        sys.exit(f"recall@6 is {recall}, below the required {args.min_recall}")
