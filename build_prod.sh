#!/bin/bash

# Exit on error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Log function
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Show usage
usage() {
    echo -e "${YELLOW}Usage: $0 [version_tag]${NC}"
    echo -e "${YELLOW}Example: $0 1.0.0${NC}"
    echo -e "${YELLOW}If no version is provided, 'latest' will be used${NC}"
    exit 1
}

# Parse arguments
VERSION=${1:-latest}

# Validate version format (optional, but recommended)
if [[ "$VERSION" != "latest" && ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    error "Invalid version format. Please use semantic versioning (e.g., 1.0.0) or 'latest'"
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    error "Docker is not running. Please start Docker and try again."
fi

# Check if buildx is available
if ! docker buildx version > /dev/null 2>&1; then
    error "Docker buildx is not available. Please install it and try again."
fi

# Create and use buildx builder if not exists
if ! docker buildx inspect multiarch > /dev/null 2>&1; then
    log "Creating new buildx builder..."
    docker buildx create --name multiarch --use
fi

# Build and push the image for both architectures
log "Building production image with version: $VERSION for multiple architectures"
docker buildx build \
    --platform linux/arm64,linux/x86_64 \
    -f Dockerfile.ubuntu \
    -t zuzyadocker/nutro-bot:$VERSION \
    --push \
    . || error "Failed to build and push image"

log "Production image successfully built and pushed to Docker Hub with version: $VERSION for both ARM64 and x86_64 architectures!" 