.PHONY: eval test lint format

eval:
	python backend/scripts/run_eval.py

test:
	pytest backend/tests/ -v

lint:
	ruff check backend
	black --check backend

format:
	ruff check --fix backend
	black backend
