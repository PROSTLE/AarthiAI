# Use an official Python runtime as a parent image
# Slim version is smaller but full version prevents some build issues with large ML libs
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies (needed for some python packages)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
# PyTroch CPU-only
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Download NLTK data (VADER lexicon) during build so we don't download at runtime
RUN python -c "import nltk; nltk.download('vader_lexicon')"

# Copy the code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Expose the port (7860 required for HuggingFace Spaces)
EXPOSE 7860

# Run the application
# We use /app/backend as part of pythonpath to find modules
ENV PYTHONPATH=/app/backend
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "7860"]
