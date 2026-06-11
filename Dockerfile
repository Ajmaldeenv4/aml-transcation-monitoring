FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e .

COPY config ./config
COPY dashboards ./dashboards
COPY data/README.md ./data/README.md

# Default command runs the API; compose overrides for the dashboards.
EXPOSE 8000 8501 8502
CMD ["uvicorn", "sentinel.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
