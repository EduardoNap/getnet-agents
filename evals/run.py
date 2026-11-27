"""Answer evaluation against the real model. Costs API credit.

    python -m evals.run                         # the development cases, 3 times each, with the judge
    python -m evals.run --only multi --repeats 1
    python -m evals.run --split blind --final   # the blind cases: once, after prompts are frozen

Each case in cases.jsonl is sent through the same graph the API uses. Plain code checks the
outcome, the agents, the tools and the facts that must appear. A second model then grades
correctness, groundedness and completeness against a reference written by hand. Everything,
including each raw response, goes to evals/reports/answers.json.


A turn is a merchant message, or {"operator": "..."}: a human agent claims the open ticket and
answers it. What is graded is the response to the last turn.
"""
import os
import tempfile

# The evaluation writes conversations and tickets to its own throwaway database.
os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="getnet-evals-"))

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections import defaultdict  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

from app import store  # noqa: E402
from app.config import settings  # noqa: E402
from app.graph import resume_after_decision, resume_after_human, run_turn  # noqa: E402
from evals import judge  # noqa: E402
from evals.metrics import wilson  # noqa: E402

HERE = Path(__file__).parent
SPECIALISTS = ("knowledge", "support")
CHECKS = ["outcome", "agents", "tools", "facts"]
GRADES = ["correct", "grounded", "complete", "useful"]
OPERATOR = "eval-operator"
NO_USAGE = {"input_tokens": 0, "output_tokens": 0, "llm_calls": 0, "estimated_cost_usd": 0.0}


def smoke_ids() -> list[str]:
    """The 12 development cases the eval workflow runs against the real model: at least one of every kind."""
    return (HERE / "smoke.txt").read_text(encoding="utf-8").split()


def gate(passed: str, min_pass: float | None) -> str | None:
    """Why the run fails the required pass rate, or None. `passed` is the summary's "10/12"."""
    done, total = map(int, passed.split("/"))
    if min_pass is None or done / total >= min_pass:
        return None
    return f"{passed} runs passed every check, below the required {min_pass:.0%}"


def select_cases(cases: list[dict], split: str, only: str | None, final: bool, ids: list[str] | None = None) -> list[dict]:
    """The cases to run. Blind cases are refused without --final, and "all" is not a way around that."""
    if split == "blind" and not final:
        sys.exit("The blind cases are run once, after prompts are frozen. Add --final to do that.")
    cases = [case for case in cases if final or case["split"] != "blind"]
    cases = [case for case in cases if split in ("all", case["split"])]
    cases = [case for case in cases if ids is None or case["id"] in ids]
    return [case for case in cases if not only or case["kind"] == only]


def git_commit() -> str:
    """The commit the report was produced on, marked when the working tree differs from it."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=HERE)
        # Reports are outputs of the run itself, so they do not count as changes to what was measured.
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no", "--", ":/", ":(exclude,top)evals/reports"],
            capture_output=True, text=True, check=True, cwd=HERE,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return commit.stdout.strip() + ("+changes" if dirty.stdout.strip() else "")


def label(turn) -> str:
    return turn if isinstance(turn, str) else json.dumps(turn, ensure_ascii=False)


def outcome_of(final: dict) -> str:
    if final.get("route") == "blocked":
        return "blocked"
    return "handoff" if final.get("handoff") else "answer"


def check(case: dict, final: dict) -> dict:
    """The checks that need no model: did the request end the right way, by the right path, with the right facts."""
    steps = final.get("steps", [])
    agents = {step["agent"] for step in steps}
    tools = {tool for step in steps for tool in step.get("tools", [])}
    answer = final["response"].lower()
    checks = {
        "outcome": outcome_of(final) == case["expect"],
        "agents": set(case["expect_agents"]) <= agents,
        "tools": set(case["expect_tools"]) <= tools,
        "facts": all(any(option.lower() in answer for option in options) for options in case["must_include"])
        and not any(banned.lower() in answer for banned in case["must_not_include"]),
    }
    if "expect_actions" in case:  # how many actions the case should leave for a human to decide
        checks["actions"] = final.get("actions_created") == case["expect_actions"]
    return checks


TICKET = re.compile(r"TCK-[0-9A-F]{8}")


def ticket_evidence(response: str, issued: set[str]) -> list[dict]:
    """One evidence item for each ticket number in the response that the system really issued.
    Without it the judge marks an answer "not grounded" for quoting its own ticket; an invented number still fails."""
    return [
        {"tool": "ticket", "output": f"The system opened ticket {ticket_id} in this conversation."}
        for ticket_id in dict.fromkeys(TICKET.findall(response))
        if ticket_id in issued
    ]


def play(case: dict) -> tuple[dict, list[dict]]:
    """Send every turn of a case. Returns the state that is graded and the evidence its answer may draw on."""
    conversation_id, final, evidence = None, {}, []
    for turn in case["turns"]:
        if isinstance(turn, str):  # the merchant writes
            final = run_turn(turn, case["user"], conversation_id)
            conversation_id = final["conversation_id"]
            evidence = [item for finding in final.get("findings", []) for item in finding["evidence"]]
            if final.get("history"):  # earlier turns, a human's reply included, are a fair source for a follow-up
                evidence.insert(0, {"tool": "conversation", "output": final["history"]})
        elif "operator" in turn:  # a human agent claims the open ticket and answers it
            ticket_id = store.unresolved_ticket(conversation_id)["ticket_id"]
            store.claim_ticket(ticket_id, OPERATOR)
            resolved = resume_after_human(ticket_id, OPERATOR, turn["operator"])
            final = {**final, "response": resolved["merchant_message"], "handoff": None, "findings": [],
                     "steps": [{"agent": "resume", "tools": []}], "usage": dict(NO_USAGE)}
            evidence = [{"tool": "human_agent", "output": turn["operator"]}]
        elif "approve" in turn or "reject" in turn:  # a human agent decides the action the agent proposed
            ticket_id = _actions_of(case["user"], conversation_id)[-1]["ticket_id"]
            store.claim_ticket(ticket_id, OPERATOR)
            decided = resume_after_decision(ticket_id, OPERATOR, approved="approve" in turn, reason=turn.get("reject", ""))
            final = {**final, "response": decided["merchant_message"], "handoff": None, "findings": [],
                     "steps": [{"agent": "resume", "tools": []}], "usage": dict(NO_USAGE)}
            evidence = [{"tool": "human_agent", "output": decided["reply"]}]
        else:
            raise ValueError(f"unknown turn in case {case['id']}: {turn}")
    final["actions_created"] = len(_actions_of(case["user"], conversation_id))
    issued = {ticket["ticket_id"] for ticket in store.list_tickets() if ticket["conversation_id"] == conversation_id}
    return final, evidence + ticket_evidence(final["response"], issued)


def _actions_of(user: str, conversation_id: str) -> list[dict]:
    """The actions proposed in this conversation."""
    return [a for a in store.list_actions(user) if store.get_ticket(a["ticket_id"])["conversation_id"] == conversation_id]


def run_case(case: dict, repeat: int, with_judge: bool) -> dict:
    started = time.perf_counter()
    final, evidence = play(case)
    question = label(case["turns"][-1])
    result = {
        "id": case["id"],
        "kind": case["kind"],
        "split": case["split"],
        "repeat": repeat,
        "message": question,
        "response": final["response"],
        "path": [step["agent"] + (f"[{','.join(step['tools'])}]" if step.get("tools") else "") for step in final["steps"]],
        "specialist_runs": sum(step["agent"] in SPECIALISTS for step in final["steps"]),
        "sources": final.get("sources", []),
        "verifier": next(({"status": s["status"], "removed": s.get("removed", [])} for s in final["steps"] if s["agent"] == "verifier"), None),
        "handoff": final.get("handoff"),
        "usage": final["usage"],
        "seconds": round(time.perf_counter() - started, 1),
        "trace_id": final["trace_id"],
        "evidence": evidence,  # complete, exactly as the judge saw it
        "checks": check(case, final),
    }
    if with_judge and case["expect"] == "answer":
        verdict = judge.grade(question, case["reference"], final["response"], evidence)
        result["judge"] = verdict.model_dump()
    result["passed"] = all(result["checks"].values()) and all(result.get("judge", {}).get(g, True) for g in GRADES)
    return result


def run_case_safely(case: dict, repeat: int, with_judge: bool) -> dict:
    try:
        return run_case(case, repeat, with_judge)
    except Exception as exc:  # recorded as a failed run, with the error
        return {
            "id": case["id"], "kind": case["kind"], "split": case["split"], "repeat": repeat,
            "message": label(case["turns"][-1]), "response": "", "path": [], "specialist_runs": 0, "sources": [],
            "handoff": None, "usage": {"estimated_cost_usd": 0.0}, "seconds": 0.0, "trace_id": "", "evidence": [],
            "checks": dict.fromkeys(CHECKS, False), "error": f"{type(exc).__name__}: {exc}", "passed": False,
        }


def rate(results: list[dict], read) -> str:
    values = [read(r) for r in results if read(r) is not None]
    return f"{sum(values)}/{len(values)}" if values else "-"


def summarise(results: list[dict]) -> dict:
    by_kind = defaultdict(list)
    for result in results:
        by_kind[result["kind"]].append(result)
        by_kind["all"].append(result)
        by_kind[f"split={result['split']}"].append(result)
    table = {}
    for kind, rows in by_kind.items():
        table[kind] = {
            "runs": len(rows),
            "passed": rate(rows, lambda r: r["passed"]),
            **{name: rate(rows, lambda r, name=name: r["checks"].get(name)) for name in CHECKS},
            **{name: rate(rows, lambda r, name=name: r.get("judge", {}).get(name)) for name in GRADES},
        }
    by_case = defaultdict(list)
    for result in results:
        by_case[result["id"]].append(result["passed"])
    seconds = sorted(r["seconds"] for r in results)
    checked = [r["verifier"]["status"] for r in results if r.get("verifier")]
    return {
        "verifier": {status: checked.count(status) for status in sorted(set(checked))},
        "by_kind": table,
        "cases": len(by_case),
        "cases_passing_every_repeat": sum(all(passes) for passes in by_case.values()),
        "cases_with_mixed_results": sorted(case for case, passes in by_case.items() if len(set(passes)) > 1),
        "cases_failing_every_repeat": sorted(case for case, passes in by_case.items() if not any(passes)),
        "seconds_median": statistics.median(seconds),
        "seconds_p95": seconds[int(0.95 * (len(seconds) - 1))],
        "cost_usd_per_request": round(statistics.mean(r["usage"]["estimated_cost_usd"] for r in results), 4),
    }


def interval(fraction: str) -> str:
    """"9/10" -> "60%–98%"."""
    if "/" not in fraction:
        return "-"
    low, high = wilson(*map(int, fraction.split("/")))
    return f"{low:.0%}–{high:.0%}"


def as_markdown(report: dict) -> str:
    summary, meta = report["summary"], report["meta"]
    columns = ["runs", "passed", *CHECKS, *GRADES]
    lines = [
        "# Answer evaluation",
        "",
        f"Run on {meta['date']} with `{meta['model']}` answering and `{meta['judge_model']}` judging. "
        f"{summary['cases']} cases ({meta['split']}), {meta['repeats']} runs each, at commit `{meta.get('commit', 'unknown')}`. Raw results are in the `.json` file next to this one.",
        "",
        "`outcome`, `agents`, `tools` and `facts` are checked by code. "
        "`correct`, `grounded`, `complete` and `useful` are the judge's verdicts on the cases that end in an answer. "
        "A run passes when all of them hold. The interval rows give the 95% Wilson interval of each rate.",
        "",
        "| Kind | " + " | ".join(columns) + " |",
        "|---|" + "---|" * len(columns),
    ]
    order = lambda item: (item[0] != "all", not item[0].startswith("split="), item[0])  # noqa: E731
    for kind, row in sorted(summary["by_kind"].items(), key=order):
        lines.append(f"| {kind} | " + " | ".join(str(row[column]) for column in columns) + " |")
        if kind == "all" or kind.startswith("split="):
            lines.append(f"| {kind}, 95% interval | | " + " | ".join(interval(row[column]) for column in columns[1:]) + " |")
    lines += [
        "",
        f"- Cases passing on every run: {summary['cases_passing_every_repeat']} of {summary['cases']}.",
        f"- Cases whose result changed between runs: {', '.join(summary['cases_with_mixed_results']) or 'none'}.",
        f"- Cases failing on every run: {', '.join(summary['cases_failing_every_repeat']) or 'none'}.",
        f"- Verifier, by outcome: {summary.get('verifier') or 'not run'}.",
        f"- Time per case: median {summary['seconds_median']} s, 95th percentile {summary['seconds_p95']} s.",
        f"- Estimated cost: ${summary['cost_usd_per_request']} per request (answering only; tokens at list price).",
        "",
        "## Runs that did not pass",
        "",
    ]
    failed = [r for r in report["results"] if not r["passed"]]
    for r in failed:
        why = [name for name, ok in r["checks"].items() if not ok] + [g for g in GRADES if r.get("judge", {}).get(g) is False]
        detail = r.get("error") or r.get("judge", {}).get("reason", "")
        lines.append(f"- `{r['id']}` run {r['repeat']}: failed {', '.join(why)}. {detail}")
    return "\n".join(lines + ([] if failed else ["None."])) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--only", help="run one kind of case, for example multi")
    parser.add_argument("--split", default="dev", choices=["dev", "blind", "all"])
    parser.add_argument("--final", action="store_true", help="allow the blind cases; for the one run after prompts are frozen")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--name", default="answers", help="report file name, without extension")
    parser.add_argument("--smoke", action="store_true", help="run only the 12 cases listed in smoke.txt")
    parser.add_argument("--min-pass", type=float, help="fail (exit 1) when the share of runs passing every check is below this")
    args = parser.parse_args()

    if not args.no_judge:
        judge.require_independent(settings.judge_model, [settings.model, settings.router_model, settings.verifier_model])
    cases = [json.loads(line) for line in (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = select_cases(cases, args.split, args.only, args.final, smoke_ids() if args.smoke else None)
    jobs = [(case, repeat) for case in cases for repeat in range(1, args.repeats + 1)]
    # Approval cases run one at a time: a second request for the same terminal while the first is pending
    # returns the pending one, which is right for the service and would blur which run proposed it.
    together = [job for job in jobs if job[0]["kind"] != "approval"]
    one_by_one = [job for job in jobs if job[0]["kind"] == "approval"]
    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(lambda job: run_case_safely(*job, with_judge=not args.no_judge), together))
    results += [run_case_safely(*job, with_judge=not args.no_judge) for job in one_by_one]

    report = {
        "meta": {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "commit": git_commit(),
            "model": settings.model,
            "router_model": settings.router_model,
            "judge_model": settings.judge_model,
            "repeats": args.repeats,
            "split": args.split,
        },
        "summary": summarise(results),
        "results": results,
    }
    (HERE / "reports").mkdir(exist_ok=True)
    (HERE / "reports" / f"{args.name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "reports" / f"{args.name}.md").write_text(as_markdown(report), encoding="utf-8")
    print(as_markdown(report))
    if failure := gate(report["summary"]["by_kind"]["all"]["passed"], args.min_pass):
        sys.exit(failure)
