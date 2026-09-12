# AlphaDex Scout application image.
# Reproducible build via uv + committed uv.lock. Configuration is provided at
# runtime through environment variables (never baked into the image).

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# uv for dependency management.
RUN pip install --no-cache-dir uv

# Install dependencies first (better layer caching) using the lockfile.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application source + migrations. README.md is required because pyproject.toml
# declares it as the project readme, and building/installing the project reads it.
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY README.md ./README.md

# Install the project itself into the environment.
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

# Apply migrations, then serve. DATABASE_URL / POSTGRES_* come from the environment.
CMD ["sh", "-c", "alembic upgrade head && uvicorn alphadex.api.app:app --host 0.0.0.0 --port 8000"]
