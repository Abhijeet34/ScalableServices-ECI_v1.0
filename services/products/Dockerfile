FROM python:3.11-slim

WORKDIR /app

# Build metadata
ARG RELEASE_ID=dev
ENV RELEASE_ID=${RELEASE_ID}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy service requirements
COPY services/products/pyproject.toml .

# Install Python dependencies with BuildKit cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -e .

# Copy shared code
COPY shared /app/shared

# Copy service code
COPY services/products/app /app/app
COPY services/products/alembic.ini /app/ 
COPY services/products/alembic /app/alembic

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
