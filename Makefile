# Everyday commands. Run `make help` for the list.

LIVE = BODHAN_BASE_URL=https://api.bodhan.ai OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

.PHONY: help install mock backend backend-live frontend test test-fast lint format typecheck check refresh-documents

help:  ## list the commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/'

install:  ## Python and Node dependencies, and the offline dictionary data
	uv sync
	npm install --prefix frontend
	uv run python -m nltk.downloader -q wordnet

mock:  ## the mock Bodhan + OpenRouter server on :9000 (free)
	uv run uvicorn mock_server.app:app --port 9000

backend:  ## the API on :8000, against the mock unless .env points elsewhere
	uv run uvicorn backend.main:app --port 8000 --reload --reload-dir backend

backend-live:  ## the API on :8000 against the real Bodhan and OpenRouter (keys from .env; spends credits)
	$(LIVE) uv run uvicorn backend.main:app --port 8000

frontend:  ## the studio on http://localhost:5173
	npm run dev --prefix frontend

test:  ## every test, including the one that launches Chrome
	uv run pytest

test-fast:  ## every test except the one that launches Chrome
	uv run pytest -m "not slow"

lint:  ## Python lint and format check, frontend lint
	uv run ruff check .
	uv run ruff format --check .
	npm run --prefix frontend lint

format:  ## format the Python code
	uv run ruff format .
	uv run ruff check --fix .

typecheck:  ## type-check the frontend
	npm run --prefix frontend typecheck

check: lint typecheck test-fast  ## everything a change should pass

refresh-documents:  ## re-ingest and re-translate every stored document (run after ingest changes; backend running)
	uv run scripts/refresh_documents.py
