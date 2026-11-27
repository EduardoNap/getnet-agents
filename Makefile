# One command per job. `make test` needs only Python 3.12: no API key, no Docker.
PYTHON ?= $(shell command -v python3.12 || command -v python3)
BIN := .venv/bin

.PHONY: test eval-offline eval-smoke demo

# The virtualenv, rebuilt when requirements.txt changes.
$(BIN)/.installed: requirements.txt
	$(PYTHON) -m venv .venv
	$(BIN)/pip install --quiet -r requirements.txt
	touch $@

# Unit and integration tests: the real graph, tools, store and API with the model replaced.
test: $(BIN)/.installed
	$(BIN)/python -m pytest

# The evaluations that need no model: retrieval on the labelled questions, and the guardrail's phrase layer.
# Reports go to evals/reports/offline_*, so the committed reports of the final runs are not replaced.
eval-offline: $(BIN)/.installed
	$(BIN)/python -m evals.retrieval --min-recall 0.90 --name offline_retrieval
	$(BIN)/python -m evals.guardrails --max-false-blocks 0.05 --name offline_guardrails

# The same check the eval workflow runs when started by hand, against the real model. Needs ANTHROPIC_API_KEY; costs about $1.50.
eval-smoke: $(BIN)/.installed
	$(BIN)/python -m evals.run --smoke --repeats 1 --min-pass 0.80 --name smoke_answers
	$(BIN)/python -m evals.guardrails --with-router --min-blocked 0.95 --max-false-blocks 0.05 --name smoke_guardrails
	$(BIN)/python -m evals.retrieval --min-recall 0.90 --name smoke_retrieval

# Starts the service in Docker and sends the challenge's example questions to it. Needs .env with the API key.
demo:
	docker compose up --build --detach --wait
	./scripts/demo.sh
