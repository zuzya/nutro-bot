#!/bin/bash

# Set platform
PLATFORM="linux/amd64"

# Set Docker build timeout and configuration
export DOCKER_BUILDKIT=1
export BUILDKIT_INLINE_CACHE=1
export DOCKER_CLIENT_TIMEOUT=1800
export COMPOSE_HTTP_TIMEOUT=1800
export DOCKER_BUILD_TIMEOUT=1800

# Configure Docker daemon for better connectivity
sudo mkdir -p /etc/docker
cat << EOF | sudo tee /etc/docker/daemon.json
{
  "max-concurrent-downloads": 3,
  "max-download-attempts": 5,
  "registry-mirrors": [
    "https://mirror.gcr.io",
    "https://registry-1.docker.io",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com",
    "https://docker.mirrors.sjtug.sjtu.edu.cn",
    "https://registry.docker-cn.com"
  ],
  "dns": [
    "8.8.8.8",
    "8.8.4.4",
    "1.1.1.1",
    "1.0.0.1",
    "208.67.222.222",
    "208.67.220.220",
    "9.9.9.9",
    "149.112.112.112"
  ],
  "experimental": true,
  "features": {
    "buildkit": true
  }
}
EOF

# Restart Docker daemon
sudo systemctl restart docker

# Wait for Docker to be ready
sleep 10

# Remove existing builder if it exists
docker buildx rm multiarch-builder || true

# Create and use buildx builder with local cache
docker buildx create --use --name multiarch-builder --driver docker-container --driver-opt network=host --driver-opt image=moby/buildkit:master
docker buildx inspect --bootstrap

# Build the image with retry logic
max_retries=1
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    echo "Attempt $((retry_count + 1)) of $max_retries"
    
    # Try to pull the base image first with retries
    echo "Pulling base image..."
    for i in {1..5}; do
        echo "Pull attempt $i..."
        if docker pull --platform ${PLATFORM} alpine:3.19; then
            echo "Pull successful!"
            break
        fi
        echo "Pull attempt $i failed, retrying in 10 seconds..."
        sleep 10
    done
    
    # Build with local cache
    if docker buildx build \
        --platform ${PLATFORM} \
        --no-cache \
        --progress=plain \
        -f Dockerfile.ubuntu \
        -t nutro-bot-bot \
        -t zuzyadocker/nutro-bot:amd64 \
        --load \
        --cache-from type=local,src=/tmp/.buildx-cache \
        --cache-to type=local,dest=/tmp/.buildx-cache \
        .; then
        echo "Build successful!"
        exit 0
    else
        echo "Build failed, retrying..."
        retry_count=$((retry_count + 1))
        sleep 20
    fi
done

echo "Build failed after $max_retries attempts"
exit 1 