.PHONY: lint fmt worker

lint:
	poetry run ruff check .
	poetry run black --check .
	poetry run ty check .

fmt:
	poetry run ruff check --fix .
	poetry run black .

worker:
	poetry run python worker.py
