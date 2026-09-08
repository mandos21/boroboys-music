FROM python:3.12-slim

ENV POETRY_VERSION=2.1.1 \
    POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PATH="/opt/poetry/bin:/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # uvicorn puts the working directory on sys.path itself, but the
    # procrastinate console script does not, so the worker could not import
    # app.tasks without this.
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSL https://install.python-poetry.org | python3 - --version "$POETRY_VERSION"

COPY pyproject.toml poetry.lock* ./
RUN poetry install --only main --no-root

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

# Nothing at runtime writes into /app, so the process does not need to own it.
RUN useradd --system --uid 10001 --create-home app
USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
