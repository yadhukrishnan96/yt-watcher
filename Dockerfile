# ── Stage 1: build deps ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1


COPY requirements.txt .


RUN pip install --upgrade pip \
 && pip install --prefix=/install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

# Security: run as non-root
RUN addgroup --system app && adduser --system --ingroup app --uid 1000 app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/ ./app/

# Ownership
RUN chown -R app:app /app
USER 1000

EXPOSE 8000

# Uvicorn with 1 worker — horizontal scaling is done at the Pod level in k8s
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
