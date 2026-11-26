# syntax=docker/dockerfile:1
# Build context: apps/api
FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:3.13.18-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13.18-slim-trixie AS runtime
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/artifacts && chown 10001:10001 /data/artifacts && chmod 750 /data/artifacts
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "webforge_api.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--no-access-log"]
