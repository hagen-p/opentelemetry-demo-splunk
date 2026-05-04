# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
#
# Stub gRPC server for standalone dc-shim testing.
# Implements CartService + CheckoutService with minimal valid responses.
#
# Build:
#   docker build -t dc-shim-stub:latest -f test/dc-shim-standalone/Dockerfile test/dc-shim-standalone/
#
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto and compile gRPC stubs
COPY demo.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. demo.proto

COPY stub-server.py .

EXPOSE 8080

USER nobody
CMD ["python", "stub-server.py"]
