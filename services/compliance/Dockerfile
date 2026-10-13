FROM python:3.13-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY services/compliance/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project (needed for src/ imports)
COPY . .

# Run the compliance service
CMD ["python", "services/compliance/main.py"]
