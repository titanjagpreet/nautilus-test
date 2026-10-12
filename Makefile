# Strategy Lab Prototype -- one-command tasks. Run `make help` for the list.
SHELL := /bin/bash
UV ?= uv
PY := $(UV) run python

.PHONY: help setup network data lint test demo bench parity eval ui

help:  ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

setup:  ## Install pinned deps (uv sync), git hooks, UI libraries (offline copy), .env template
	$(UV) sync --frozen
	$(UV) run pre-commit install
	$(PY) scripts/vendor_assets.py
	@test -f .env || cp .env.example .env

network:  ## Check HTTPS reachability of every data / LLM / CDN host
	$(PY) scripts/check_network.py

data:  ## Download, validate and resample BTC/XAU history; writes data/quality_report.md
	$(PY) -m strategy_lab.data

lint:  ## ruff + mypy
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy strategy_lab scripts benchmarks

test:  ## Run the test suite
	$(UV) run pytest -n auto

demo:  ## End to end on the downloaded data: catalogue, both engines, lab, AI (if a key is set)
	$(PY) scripts/demo.py

bench:  ## Speed + memory of both engines (1 backtest, 144 and 1,600-run sweeps; hours) -> REPORT.md
	$(PY) benchmarks/bench.py

parity:  ## Fast engine vs Nautilus on the 10 catalogue strategies over 2024 -> REPORT.md
	$(PY) benchmarks/parity_report.py

eval:  ## AI builder eval on every provider with a key in .env (spend-capped at $1) -> REPORT.md
	$(PY) -m strategy_lab.ai.evaluation

ui:  ## Web UI + API on http://127.0.0.1:8000 (Builder, Backtest, Lab, Compare, Costs)
	$(UV) run uvicorn strategy_lab.api.app:app --host 127.0.0.1 --port 8000
