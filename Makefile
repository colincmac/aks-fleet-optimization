.PHONY: install test lint typecheck analyze verify ui-verify

PYTHON ?= python

install:
	$(PYTHON) -m pip install -e '.[dev,kubernetes]'

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy src scripts

analyze:
	$(PYTHON) -m aks_fleet_efficiency.cli analyze --snapshot examples/fixtures/fleet-snapshot.json --config examples/advisor-config.yaml --output report.md

verify:
	$(PYTHON) scripts/verify.py

ui-verify:
	npm --prefix plugins/headlamp-fleet-efficiency run verify
	npm --prefix plugins/headlamp-fleet-efficiency run test:e2e
