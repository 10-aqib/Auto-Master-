# syntax=docker/dockerfile:1
# Build context: apps/browser. Isolated browser sandbox: no secrets, internal network only.
FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --python /usr/bin/python3
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable --python /usr/bin/python3
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /app
USER pwuser
EXPOSE 9000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "webforge_browser.app:app", "--host", "0.0.0.0", "--port", "9000", "--no-server-header", "--no-access-log"]
