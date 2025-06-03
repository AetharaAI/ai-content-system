FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt* ./
RUN pip install --no-cache-dir -r requirements.txt || echo "No requirements.txt found"

# Copy source code
COPY . .

# Expose common port
EXPOSE 8000

# Default command
CMD ["python", "main.py"]
