FROM python:3.9-slim-bullseye AS base
WORKDIR /usr/src/app

# Install and Configure Poetry
ENV POETRY_VERSION=1.4.2
ENV POETRY_HOME=/opt/poetry
RUN apt-get update && apt-get install -y curl
RUN curl -sSL https://install.python-poetry.org | python -
ENV PATH="/opt/poetry/bin:$PATH"
RUN poetry config virtualenvs.in-project true

# Setup project
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-dev

# Final Image
FROM python:3.9-slim-bullseye AS final
WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y curl
RUN useradd -ms /bin/sh indy

ENV WAIT_VERSION 2.7.2
ADD https://github.com/ufoscout/docker-compose-wait/releases/download/$WAIT_VERSION/wait /wait
RUN chmod +x /wait
USER indy

COPY --from=base /usr/src/app/.venv /usr/src/app/.venv
ENV PATH="/usr/src/app/.venv/bin:$PATH"

COPY ./main.py main.py
ENTRYPOINT ["/bin/sh", "-c", "/wait && python main.py \"$@\"", "--"]
