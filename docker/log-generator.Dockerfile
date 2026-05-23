ARG PYTHON_BASE_IMAGE=python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements/generator.txt requirements/generator.txt
RUN pip install --no-cache-dir -r requirements/generator.txt

COPY log-generator log-generator

CMD ["python", "log-generator/run_continuous.py"]
