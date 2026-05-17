FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY tailmate-db-gateway/requirements.txt ./tailmate-db-gateway/requirements.txt
COPY tailmate-db-gateway/main.py ./tailmate-db-gateway/main.py

RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir -r tailmate-db-gateway/requirements.txt

WORKDIR /app/tailmate-db-gateway
CMD exec gunicorn --bind :$PORT --workers 1 --threads 2 --timeout 0 main:app
