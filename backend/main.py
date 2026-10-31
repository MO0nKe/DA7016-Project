"""Panna API, the uvicorn entry point.

uv run uvicorn backend.main:app --port 8000      (with the mock server on :9000, or live APIs set in .env)
"""

from .app import create_app

app = create_app()
