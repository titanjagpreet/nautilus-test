# Strategy Lab Prototype -- one-command tasks. Run `make help` for the list.
SHELL := /bin/bash
UV ?= uv
PY := $(UV) run python

.PHONY: help setup network data lint test

help:  ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

setup:  ## Install pinned deps (uv sync), git hooks, .env template
	$(UV) sync --frozen
	$(UV) run pre-commit install
	@test -f .env || cp .env.example .env

network:  ## Check HTTPS reachability of every data / LLM / CDN host
	$(PY) scripts/check_network.py

data:  ## Download, validate and resample BTC/XAU history; writes data/quality_report.md
	$(PY) -m strategy_lab.data

lint:  ## ruff + mypy
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy strategy_lab scripts

test:  ## Run the test suite
	$(UV) run pytest -n auto
