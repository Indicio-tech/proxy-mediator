FROM python:3.7-alpine AS base
WORKDIR /usr/src/app
RUN apk update && \
  apk add \
  build-base \
  curl \
  git \
  libffi-dev \
  openssh-client \
  postgresql-dev

ENV POETRY_HOME=/opt/poetry \
    VENV=/usr/src/app/.venv
ENV PATH="$POETRY_HOME/bin:$VENV/bin:$PATH"

RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/install-poetry.py | python -
RUN poetry config virtualenvs.create true; poetry config virtualenvs.in-project true

COPY ./pyproject.toml ./poetry.lock ./
RUN poetry install --no-dev

FROM python:3.7-alpine as main
WORKDIR /usr/src/app
COPY --from=base /usr/src/app /usr/src/app
ENV PATH="/usr/src/app/.venv/bin:$PATH"

ENV WAIT_VERSION 2.7.2
ADD https://github.com/ufoscout/docker-compose-wait/releases/download/$WAIT_VERSION/wait /wait
RUN chmod +x /wait

COPY ./main.py main.py

ENTRYPOINT ["/bin/sh", "-c", "/wait && python main.py \"$@\"", "--"]