"""Grade stored answers. The answers are not regenerated.

    python -m evals.regrade --db /path/to/the/run's/app.db


The report as first written is kept as answers_as_run.json / .md.
"""
import argparse
import json
import sqlite3
from pathlib import Path

from evals import judge
from evals.run import GRADES, as_markdown, summarise, ticket_evidence

HERE = Path(__file__).parent


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="the SQLite file the evaluation run wrote its tickets to")
    parser.add_argument("--name", default="answers")
    args = parser.parse_args()

    path = HERE / "reports" / f"{args.name}.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in map(json.loads, (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines())}
    issued = {row[0] for row in sqlite3.connect(args.db).execute("SELECT ticket_id FROM tickets")}

    regraded = []
    for result in report["results"]:
        extra = ticket_evidence(result["response"], issued)
        if not extra or "judge" not in result:
            continue
        result["evidence"] = result["evidence"] + extra
        result["judge_as_run"] = result["judge"]
        result["judge"] = judge.grade(result["message"], cases[result["id"]]["reference"], result["response"], result["evidence"]).model_dump()
        result["passed"] = all(result["checks"].values()) and all(result["judge"].get(g, True) for g in GRADES)
        regraded.append(f"{result['id']}#{result['repeat']}")

    report["meta"]["regraded"] = regraded
    report["summary"] = summarise(report["results"])
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    note = (
        f"\n## Graded again\n\n{len(regraded)} stored answers that quote a ticket number were graded again with the fact that the system "
        "issued that ticket added to the evidence (`python -m evals.regrade`). No answer was regenerated. "
        f"The report as first written is `{args.name}_as_run.md`.\n\n" + ", ".join(regraded) + "\n"
    )
    (HERE / "reports" / f"{args.name}.md").write_text(as_markdown(report) + note, encoding="utf-8")
    print(as_markdown(report).split("## Runs that did not pass")[0] + note)
