"""ASGI entrypoint: `uvicorn webforge_api.asgi:app`. Fails fast on invalid settings."""

from webforge_api.main import create_app

app = create_app()
