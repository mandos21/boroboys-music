FROM python:3.12-slim

ENV POETRY_VERSION=2.0.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PATH="/opt/poetry/bin:/app/.venv/bin:$PATH"

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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
