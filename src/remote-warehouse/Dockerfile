# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY demo.proto .
COPY generate_proto.sh .
COPY consumer.py .

# Generate protobuf files
RUN chmod +x generate_proto.sh && ./generate_proto.sh

# Run as non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Run the consumer
CMD ["python3", "consumer.py"]
