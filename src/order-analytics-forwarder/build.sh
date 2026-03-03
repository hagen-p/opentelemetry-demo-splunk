#!/bin/bash
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Build script for order-analytics-forwarder service

set -e

# Configuration
IMAGE_NAME="${IMAGE_NAME:-ghcr.io/splunk/opentelemetry-demo/otel-order-analytics-forwarder}"
VERSION="${VERSION:-1.6.0}"

echo "Building order-analytics-forwarder Docker image..."
echo "Image: ${IMAGE_NAME}:${VERSION}"

# Build from repository root
cd "$(git rev-parse --show-toplevel)"

docker build \
  -f src/order-analytics-forwarder/Dockerfile \
  -t "${IMAGE_NAME}:${VERSION}" \
  -t "${IMAGE_NAME}:latest" \
  .

echo "✓ Build complete: ${IMAGE_NAME}:${VERSION}"
echo ""
echo "To push the image:"
echo "  docker push ${IMAGE_NAME}:${VERSION}"
echo "  docker push ${IMAGE_NAME}:latest"
echo ""
echo "To run locally:"
echo "  docker run --rm -it \\"
echo "    -e KAFKA_ADDR=localhost:9092 \\"
echo "    -e OTEL_SERVICE_NAME=order-analytics-forwarder \\"
echo "    -e LAMBDA_FUNCTION_NAME=order-analytics-processor \\"
echo "    -e AWS_REGION=us-east-1 \\"
echo "    -e AWS_ACCESS_KEY_ID=\$AWS_ACCESS_KEY_ID \\"
echo "    -e AWS_SECRET_ACCESS_KEY=\$AWS_SECRET_ACCESS_KEY \\"
echo "    ${IMAGE_NAME}:${VERSION}"
