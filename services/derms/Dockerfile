FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project for access to src/ modules
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Run DERMS service
CMD ["python", "services/derms/main.py"]
