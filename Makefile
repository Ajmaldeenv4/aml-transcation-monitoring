# Sentinel AML — developer commands
# On Windows, run these via `make` (Git Bash / WSL) or invoke the underlying
# commands directly in PowerShell.

.PHONY: setup test lint fmt run-api run-analyst run-mi rules clean

setup:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src tests

fmt:
	ruff format src tests
	ruff check --fix src tests

run-api:
	uvicorn sentinel.api.main:app --reload --port 8000

run-analyst:
	streamlit run dashboards/analyst_app.py --server.port 8501

run-mi:
	streamlit run dashboards/mi_app.py --server.port 8502

rules:
	python -m sentinel.cli run-rules

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ *.egg-info
