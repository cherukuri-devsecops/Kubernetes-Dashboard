FROM python:3.12-slim-bookworm

WORKDIR /app

# Patch OS-level vulnerabilities in the base image
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Drop privileges — run as non-root
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy only the app package (includes templates/ and static/)
COPY --chown=appuser:appgroup app/ ./app/

# SQLite data directory (override via SQLITE_PATH env var if needed)
RUN mkdir -p /data && chown appuser:appgroup /data
VOLUME ["/data"]

USER appuser

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 5000

# Use gunicorn + gevent workers so SSE log streams don't block other requests
CMD ["gunicorn", "-w", "4", "-k", "gevent", "--worker-connections", "1000", "-b", "0.0.0.0:5000", "--timeout", "120", "--log-level", "info", "app.main:app"]
