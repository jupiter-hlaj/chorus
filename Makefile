.PHONY: build test lint local-dev local-lambda deploy-dev

build:
	sam build --template template.yaml --use-container

test:
	pytest tests/ -v --tb=short

lint:
	ruff check src/ && ruff format --check src/ && bandit -r src/ -ll

local-dev:
	uvicorn src.app:app --reload --port 8000

local-lambda:
	sam local start-api --template template.yaml --env-vars local.env.json

deploy-dev:
	sam deploy --config-env dev
