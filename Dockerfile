# Start with a stable Debian-based Python image
FROM python:3.11-slim-bookworm

# 1. Install system dependencies
RUN apt-get update && apt-get install -y \
         build-essential \
         python3-dev \
         python3-tk \
         libusb-dev \
         libudev-dev \
         pkg-config \
         libx11-6 \
         libxext6 \
         libxrender1 \
         && rm -rf /var/lib/apt/lists/*

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Install Python requirements
# We copy requirements first to leverage Docker's layer caching
COPY requirements/ /app/requirements/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel cython && \
    pip install --no-cache-dir -r requirements/linux.txt

# 4. Copy the rest of your software into the container
COPY . /app

# 5. Define the command to run your app
# Ensure 'main.py' matches your actual entry point script
CMD ["python", "SV.py"]
