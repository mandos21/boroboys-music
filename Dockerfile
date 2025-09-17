# syntax=docker/dockerfile:1
FROM python:3.11-slim as base

ENV POETRY_VERSION=1.8.3 \
    POETRY_HOME=/opt/poetry \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ENV PATH="$POETRY_HOME/bin:/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libffi-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python - --version $POETRY_VERSION

COPY pyproject.toml ./

RUN poetry install --no-root --no-ansi

COPY app ./app
COPY docs ./docs
COPY tests ./tests
COPY README.md .
COPY .env.example .

RUN poetry install --no-ansi

ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

CMD ["poetry", "run", "streamlit", "run", "app/streamlit_app.py"]
