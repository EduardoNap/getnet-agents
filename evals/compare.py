"""Two answer reports side by side: quality, cost and latency.

    python -m evals.compare evals/reports/answers.json evals/reports/answers_sonnet.json
"""
import json
import sys
from pathlib import Path

ROWS = ["passed", "outcome", "agents", "tools", "facts", "correct", "grounded", "complete"]


def compare(first: dict, second: dict) -> str:
    reports = [first, second]
    lines = ["| | " + " | ".join(report["meta"]["model"] for report in reports) + " |", "|---|---|---|"]
    for row in ROWS:
        lines.append(f"| {row} | " + " | ".join(str(report["summary"]["by_kind"]["all"].get(row, "-")) for report in reports) + " |")
    lines.append("| cost per request | " + " | ".join(f"${report['summary']['cost_usd_per_request']}" for report in reports) + " |")
    lines.append("| seconds, median | " + " | ".join(str(report["summary"]["seconds_median"]) for report in reports) + " |")
    lines.append("| seconds, 95th percentile | " + " | ".join(str(report["summary"]["seconds_p95"]) for report in reports) + " |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(compare(*(json.loads(Path(path).read_text(encoding="utf-8")) for path in sys.argv[1:3])))
