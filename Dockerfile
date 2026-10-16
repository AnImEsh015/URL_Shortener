# Dockerfile for URL Shortener backend service
FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr and writing pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install curl for healthchecks and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, database migrations, and startup script
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8000

# Default command runs alembic migrations, background celery worker, and uvicorn
# (Overridden in docker-compose.yml for separated local dev containers)
CMD ["./start.sh"]
