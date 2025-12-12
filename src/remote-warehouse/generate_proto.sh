#!/bin/bash
# Generate Python protobuf files from demo.proto

set -e

echo "Generating Python protobuf files..."
python3 -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    demo.proto

echo "Protobuf files generated successfully"
