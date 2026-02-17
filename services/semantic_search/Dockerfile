FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY . /app/services/semantic_search/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 9514

# Run the service
CMD ["python", "-m", "services.semantic_search.search_api"]
