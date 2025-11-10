FROM python:3.11-slim

WORKDIR /app

# Build metadata
ARG RELEASE_ID=dev
ENV RELEASE_ID=${RELEASE_ID}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/seed/pyproject.toml .

# Install Python dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -e .

# Copy seed data and script
# Note: In local development, docker-compose.yml overrides these with volume mounts
# In production/K8s, these COPY commands bake data into the image
COPY services/seed/eci_seed_data /app/eci_seed_data
COPY services/seed/seed.py /app/

# Run seed script
CMD ["python", "seed.py"]
