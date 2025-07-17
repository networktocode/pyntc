ARG PYTHON_VER=3.11

FROM python:${PYTHON_VER}-slim

RUN which poetry || curl -sSL https://install.python-poetry.org | python3 -

WORKDIR /local
COPY . /local

RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --with dev
