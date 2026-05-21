FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements/backend.txt requirements/backend.txt
COPY requirements/test.txt requirements/test.txt
RUN pip install --no-cache-dir -r requirements/backend.txt -r requirements/test.txt

COPY src src
COPY tests tests

CMD ["pytest", "-q"]
