.PHONY: help install test unit functional sim report lint typecheck coverage clean all

PYTHON ?= python3
export PYTHONPATH := src:.

help:
	@echo "make install     install the package and dev extras"
	@echo "make test        run the full suite (unit + functional)"
	@echo "make unit        unit tests only"
	@echo "make functional  functional tests only"
	@echo "make sim         run every example in the book"
	@echo "make report      run every example and write report.html"
	@echo "make lint        ruff"
	@echo "make typecheck   mypy"
	@echo "make coverage    tests with a coverage report"
	@echo "make all         lint, typecheck, test, sim"

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests

unit:
	$(PYTHON) -m pytest tests/unit

functional:
	$(PYTHON) -m pytest tests/functional

sim:
	$(PYTHON) -m simulator.app run --all

report:
	$(PYTHON) -m simulator.app run --all --html report.html --json-out report.json

lint:
	$(PYTHON) -m ruff check src chapters simulator tests

typecheck:
	$(PYTHON) -m mypy

coverage:
	$(PYTHON) -m pytest tests --cov --cov-report=term-missing --cov-report=html

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage report.html report.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +

all: lint typecheck test sim
