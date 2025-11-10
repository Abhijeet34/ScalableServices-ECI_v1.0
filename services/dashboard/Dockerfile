FROM python:3.9-slim

WORKDIR /app

# Build metadata
ARG RELEASE_ID=dev
ENV RELEASE_ID=${RELEASE_ID}

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY services/dashboard/requirements.txt .
# Install Python dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

COPY services/dashboard/main.py .
COPY services/dashboard/templates ./templates

EXPOSE 8008

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008"]
