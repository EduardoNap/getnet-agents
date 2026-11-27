#!/usr/bin/env bash
# Sends the challenge's example scenarios to a running service and prints each reply.
#   ./scripts/demo.sh            all scenarios
#   ./scripts/demo.sh 3          only scenario 3
# The token comes from the demo issuer inside the container; set TOKEN to use your own.
set -euo pipefail
URL="${URL:-http://localhost:8000/chat}"
SCENARIOS="$(dirname "$0")/scenarios.jsonl"
# joao.silva is a person who may act for the merchant cliente1988 (see "members" in data/users.json).
TOKEN="${TOKEN:-$(docker compose exec -T api python -m app.devtokens joao.silva)}"

python3 - "$URL" "$SCENARIOS" "${1:-}" "$TOKEN" <<'PY'
import json, sys, urllib.request

url, path, only, token = sys.argv[1:5]
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}


def ask(message, conversation_id=None):
    payload = {"message": message, "user_id": "cliente1988"}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    reply = json.load(urllib.request.urlopen(request, timeout=300))
    path_taken = " -> ".join(
        step["agent"] + (f"[{','.join(step['tools'])}]" if step.get("tools") else "")
        for step in reply["agent_workflow"]
    )
    print(f"   path:    {path_taken}")
    print(f"   answer:  {reply['response']}")
    if reply["sources"]:
        print(f"   sources: {', '.join(reply['sources'][:3])}")
    if reply["handoff"]:
        print(f"   handoff: {reply['handoff']}")
    usage = reply["usage"]
    print(f"   usage:   {usage['llm_calls']} model calls, {usage['input_tokens']} tokens in, "
          f"{usage['output_tokens']} out, about ${usage['estimated_cost_usd']:.4f}")
    return reply["conversation_id"]


for line in open(path, encoding="utf-8"):
    scenario = json.loads(line)
    if only and str(scenario["id"]) != only:
        continue
    print(f"\n#{scenario['id']} {scenario['message']}")
    print(f"   expect:  {scenario['expect']}")
    conversation_id = ask(scenario["message"])
    if scenario.get("then"):  # a follow-up in the same conversation
        print(f"   then:    {scenario['then']}")
        ask(scenario["then"], conversation_id)
PY
