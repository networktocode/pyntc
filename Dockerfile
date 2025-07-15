ARG PYTHON_VER=3.11

FROM python:${PYTHON_VER}-slim

RUN pip install --upgrade pip \
  && pip install poetry

WORKDIR /local
COPY . /local

RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --with dev
