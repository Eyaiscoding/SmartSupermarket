FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project (to access src/ modules)
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Default command: run forecasting service
CMD ["python", "services/forecasting/main.py"]
