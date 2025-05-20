# Choose an official Python runtime as a parent image
# python:3.9-slim-buster is a good choice for a balance of size and compatibility.
FROM python:3.9-slim-buster

# Set common environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# - FFmpeg for video/audio processing
# - git for any pip installs directly from git repositories (if any in requirements.txt)
#   (Often not needed if all packages are from PyPI)
# - Other build tools might be needed if Python packages compile C extensions.
#   Start minimal and add if pip install fails.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        # Example: If a package needs git to install:
        # git \
        # Example: If a package needs C compilers:
        # build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first to leverage Docker's build cache.
# If requirements.txt doesn't change, this layer (and subsequent pip install) won't be rebuilt.
COPY requirements.txt .

# Install Python dependencies
# --no-cache-dir reduces image size by not storing the pip download cache.
# --no-compile might be considered for slightly smaller images if .pyc files aren't critical for startup.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container.
# Ensure your .dockerignore file is set up to exclude unnecessary files/dirs
# (like .git, .venv, __pycache__, static/uploads/, etc.)
COPY . .

# EXPOSE is informational. The actual port mapping is done in docker-compose.yml.
# This indicates that the application inside the container will listen on port 5102.
EXPOSE 5102

# The CMD/ENTRYPOINT will be provided by docker-compose.yml for different services (web, worker).
# No default CMD needed here if docker-compose always overrides it.
