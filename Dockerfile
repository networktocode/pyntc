ARG PYTHON_VER=3.11

FROM python:${PYTHON_VER}-slim

RUN which poetry || curl -sSL https://install.python-poetry.org | python3 - && \
    poetry config virtualenvs.create false

WORKDIR /local
COPY . /local

# Install the app
RUN poetry install --extras all --with dev
