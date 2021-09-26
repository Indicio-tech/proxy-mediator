FROM python:3.7

ADD https://github.com/stedolan/jq/releases/download/jq-1.6/jq-linux64 ./jq
RUN chmod +x ./jq

COPY docker/agent-tunnel-wait.sh ./agent-tunnel-wait.sh
RUN chmod +x agent-tunnel-wait.sh

RUN pip3 install --no-cache-dir poetry
RUN mkdir proxy_mediator; touch proxy_mediator/__init__.py
COPY pyproject.toml .
COPY poetry.lock .
COPY README.md .

RUN poetry install --no-dev
COPY proxy_mediator/ proxy_mediator/
ENTRYPOINT ["/bin/bash", "-c", "poetry run python -m proxy_mediator \"$@\"", "--"]
