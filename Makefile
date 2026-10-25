.PHONY: setup run test lint format typecheck migrate check

PY := .venv/bin/python

setup:  ## Create .venv, install dev deps, copy .env, migrate
	python3.12 -m venv .venv
	$(PY) -m pip install -r requirements/dev.txt
	@test -f .env || cp .env.example .env
	$(PY) manage.py migrate

run:  ## Start the dev server on http://127.0.0.1:8000
	$(PY) manage.py runserver

migrate:
	$(PY) manage.py migrate

test:  ## Tests with coverage (fails under 90%)
	$(PY) -m pytest

lint:  ## Lint, format check, type check
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/mypy apps config scripts

format:  ## Auto-fix lint issues and format
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

check:  ## Django system + migration checks
	$(PY) manage.py check
	$(PY) manage.py makemigrations --check --dry-run
