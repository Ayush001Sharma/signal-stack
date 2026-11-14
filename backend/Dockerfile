FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-ml.txt ./
ARG INSTALL_ML=true
RUN pip install -r requirements.txt \
 && if [ "$INSTALL_ML" = "true" ]; then pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements-ml.txt; fi
COPY . .
RUN useradd -m appuser && mkdir -p /app/data/uploads && chown -R appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
