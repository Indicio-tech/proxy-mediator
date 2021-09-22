FROM python:3.7

RUN pip3 install --no-cache-dir poetry
RUN mkdir proxy_mediator; touch proxy_mediator/__init__.py
COPY pyproject.toml .
COPY poetry.lock .
COPY README.md .

RUN poetry install --no-dev
COPY proxy_mediator/ proxy_mediator/
ENTRYPOINT ["/bin/bash", "-c", "poetry run python -m proxy_mediator \"$@\"", "--"]
