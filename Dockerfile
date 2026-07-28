# Use official slim Python runtime image
FROM python:3.11-slim

# Prevent Python from writing .pyc files & buffer stdout/stderr
# Set default PORT to 8080 (Cloud Run's default port)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

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

# Expose port 8080
EXPOSE 8080

# Run uvicorn server binding dynamically to $PORT (defaults to 8080)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
