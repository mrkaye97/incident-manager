.PHONY: lint fmt test worker api frontend openapi

lint:
	poetry run ruff check .
	poetry run black --check .
	poetry run ty check .
	cd frontend && pnpm lint && pnpm exec tsc -b

# needs the compose postgres running; creates and drops a throwaway database
test:
	poetry run pytest

fmt:
	poetry run ruff check --fix .
	poetry run black .

worker:
	poetry run python worker.py

api:
	poetry run uvicorn api:app --reload --port 8000

frontend:
	cd frontend && pnpm dev

# regenerate frontend API types from the FastAPI schema
openapi:
	poetry run python -c "import json, api; print(json.dumps(api.app.openapi()))" > frontend/openapi.json
	cd frontend && pnpm exec openapi-typescript openapi.json -o src/lib/api-schema.d.ts && rm openapi.json
