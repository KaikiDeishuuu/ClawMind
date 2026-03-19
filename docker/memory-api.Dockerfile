FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY memory_api ./memory_api

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8081
