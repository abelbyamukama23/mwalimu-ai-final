FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src

EXPOSE 8001

# Railway injects PORT; the agent serves HTTP (including SSE) on that port.
CMD ["sh", "-c", ".venv/bin/uvicorn agent_service.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
