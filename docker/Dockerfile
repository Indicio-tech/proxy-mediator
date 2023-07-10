FROM python:3.7 AS base
WORKDIR /app

# Install and Configure Poetry
ENV POETRY_VERSION=1.4.2
ENV POETRY_HOME=/opt/poetry
RUN curl -sSL https://install.python-poetry.org | python -
ENV PATH="/opt/poetry/bin:$PATH"
RUN poetry config virtualenvs.in-project true

# Setup project
RUN mkdir proxy_mediator; touch proxy_mediator/__init__.py
COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --no-dev

# Final Image
FROM python:3.7

RUN useradd -ms /bin/sh indy
USER indy

WORKDIR /app
COPY --from=base /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY proxy_mediator/ proxy_mediator/
ENTRYPOINT ["python", "-m", "proxy_mediator"]
