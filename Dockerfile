# Stage 1: Build stage (if you have build-time dependencies not needed at runtime)
# For this project, a single stage is likely sufficient for simplicity.

# Choose an official Python runtime as a parent image
# Replace 3.9 with your actual Python version (e.g., 3.8, 3.10, 3.11)
# Using -slim-buster or -slim-bullseye can result in smaller images
FROM python:3.9-slim-buster AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# - FFmpeg for video processing
# - libpq-dev if you were using PostgreSQL (not needed here for Redis)
# - Other build-essential tools might be needed for some Python packages with C extensions
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        # Add other system dependencies if your Python packages need them for compilation
        # For example: build-essential libffi-dev (often needed for cryptography, etc.)
        # However, try without them first to keep the image smaller.
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install pipenv if you were using it (you are using requirements.txt, so this is not needed)
# RUN pip install pipenv

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
# Using --no-cache-dir can make the image slightly smaller
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port Gunicorn will run on (if different from Flask dev server)
# This is informational; docker-compose will handle actual port mapping.
EXPOSE 5102 

# Default command to run when the container starts (can be overridden by docker-compose)
# This is just a placeholder; we'll define specific commands in docker-compose.yml
# For example, for the web service, it would be gunicorn.
# For the celery worker, it would be the celery command.
# CMD ["flask", "run", "--host=0.0.0.0"] 

