"""The brief's own example questions, three times each, against the real model. Costs API credit.

    python -m evals.brief

These ten questions were used while building, so they are a regression check and not a measure
of quality. Code checks that the expected agent and tool were used and that the request ended in
an answer. The judge has no reference answer here: it grades only `grounded` and `useful`.
"""
import os
import tempfile

os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="getnet-brief-"))

import json  # noqa: E402
import re  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

from app.config import settings  # noqa: E402
from app.graph import run_turn  # noqa: E402
from evals import judge  # noqa: E402
from evals.run import git_commit  # noqa: E402

HERE = Path(__file__).parent
REPEATS = 3
NO_REFERENCE = "No reference answer was written for this question. Mark correct and complete true; grade grounded and useful."


def expected(scenario: dict) -> tuple[set[str], set[str]]:
    """The agents and tools named in a scenario's `expect`, for example "knowledge [search_getnet_kb]"."""
    text = scenario["expect"]
    return set(re.findall(r"\b(knowledge|support)\b", text)), set(re.findall(r"\[(\w+)\]", text))


def run(scenario: dict, repeat: int) -> dict:
    final = run_turn(scenario["message"], "cliente1988")
    agents, tools = expected(scenario)
    steps = final["steps"]
    evidence = [item for finding in final.get("findings", []) for item in finding["evidence"]]
    verdict = judge.grade(scenario["message"], NO_REFERENCE, final["response"], evidence)
    result = {
        "id": scenario["id"], "repeat": repeat, "message": scenario["message"], "response": final["response"],
        "path": [step["agent"] + (f"[{','.join(step['tools'])}]" if step.get("tools") else "") for step in steps],
        "answered": not final.get("handoff") and final.get("route") != "blocked",
        "agents": agents <= {step["agent"] for step in steps},
        "tools": tools <= {tool for step in steps for tool in step.get("tools", [])},
        "grounded": verdict.grounded, "useful": verdict.useful, "reason": verdict.reason,
        "cost_usd": final["usage"]["estimated_cost_usd"], "evidence": evidence,
    }
    result["passed"] = all(result[check] for check in ("answered", "agents", "tools", "grounded", "useful"))
    return result


if __name__ == "__main__":
    judge.require_independent(settings.judge_model, [settings.model, settings.router_model, settings.verifier_model])
    scenarios = [json.loads(line) for line in (HERE.parent / "scripts" / "scenarios.jsonl").read_text(encoding="utf-8").splitlines()]
    examples = [s for s in scenarios if s["id"] <= 10]  # 11 to 14 are our own additions, covered by evals/cases.jsonl
    jobs = [(s, repeat) for s in examples for repeat in range(1, REPEATS + 1)]
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda job: run(*job), jobs))
    passed = sum(r["passed"] for r in results)
    lines = [
        "# The brief's example questions",
        "",
        f"Run on {datetime.now(timezone.utc).date().isoformat()} with `{settings.model}` answering and `{settings.judge_model}` judging, "
        f"at commit `{git_commit()}`. {len(examples)} questions, {REPEATS} runs each: **{passed}/{len(results)} runs passed**.",
        "",
        "| # | Question | passed | path of the first run |",
        "|---|---|---|---|",
    ]
    for scenario in examples:
        runs = [r for r in results if r["id"] == scenario["id"]]
        lines.append(f"| {scenario['id']} | {scenario['message']} | {sum(r['passed'] for r in runs)}/{len(runs)} | {' → '.join(runs[0]['path'])} |")
    failed = [r for r in results if not r["passed"]]
    lines += ["", "## Runs that did not pass", ""]
    lines += [f"- #{r['id']} run {r['repeat']}: " + ", ".join(c for c in ("answered", "agents", "tools", "grounded", "useful") if not r[c]) + f". {r['reason']}" for r in failed] or ["None."]
    report = {"meta": {"model": settings.model, "judge_model": settings.judge_model, "commit": git_commit()}, "passed": passed, "runs": len(results), "results": results}
    (HERE / "reports" / "brief.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "reports" / "brief.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
