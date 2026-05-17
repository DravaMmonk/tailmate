FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY tailmate-vertex-test-ui/requirements.txt ./tailmate-vertex-test-ui/requirements.txt
COPY tailmate-vertex-test-ui/main.py ./tailmate-vertex-test-ui/main.py

RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir -r tailmate-vertex-test-ui/requirements.txt

WORKDIR /app/tailmate-vertex-test-ui
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 180 main:app
