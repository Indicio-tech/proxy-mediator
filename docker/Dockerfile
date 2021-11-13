FROM python:3.7 AS base
WORKDIR /app

# Install and Configure Poetry
ENV POETRY_VERSION=1.1.11
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
WORKDIR /app
COPY --from=base /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

ENV WAIT_VERSION 2.7.2
ADD https://github.com/ufoscout/docker-compose-wait/releases/download/$WAIT_VERSION/wait /wait
RUN chmod +x /wait

COPY proxy_mediator/ proxy_mediator/
ENTRYPOINT ["/bin/sh", "-c", "/wait && python -m proxy_mediator \"$@\"", "--"]
