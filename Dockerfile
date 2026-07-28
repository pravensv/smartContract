# Use official slim Python runtime image
FROM python:3.11-slim

# Prevent Python from writing .pyc files & buffer stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Set working directory inside container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and contracts into container
COPY app/ ./app/
COPY contracts/ ./contracts/
COPY .env .env

# Expose port
EXPOSE 8000

# Run uvicorn server for Cloud Run / Container execution
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
