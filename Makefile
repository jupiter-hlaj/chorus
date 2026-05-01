.PHONY: install test lint run

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

test:
	.venv/bin/pytest tests/ -v --tb=short

lint:
	.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/ && .venv/bin/bandit -r src/ -ll

run:
	.venv/bin/uvicorn src.app:app --reload --host 127.0.0.1 --port 8000
