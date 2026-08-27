FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    DJANGO_SETTINGS_MODULE=platform_api.settings

# Install runtime dependencies (frozen, no dev) before copying source for caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY manage.py ./
COPY src ./src

EXPOSE 8000

# Railway injects PORT; the platform serves HTTP on that port.
# Migrations + static collection run on every start (idempotent), so no
CMD ["sh", "-c", ".venv/bin/python manage.py migrate --noinput && .venv/bin/python manage.py collectstatic --noinput && .venv/bin/python manage.py seed_geographic_units && .venv/bin/celery -A platform_api worker -Q default,ingestion --loglevel=info --concurrency=2 --detach && .venv/bin/gunicorn platform_api.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 --graceful-timeout 30"]
