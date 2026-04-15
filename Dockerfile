FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy and install dependencies first (for better layer caching)
COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]"

# Copy application code
COPY . .

# Create non-root user for running the application
RUN useradd --create-home --shell /bin/bash hcrm
USER hcrm

EXPOSE 8000

CMD ["uvicorn", "healthcare_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
