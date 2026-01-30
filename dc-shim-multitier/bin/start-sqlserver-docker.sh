#!/bin/bash
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Start SQL Server using Docker
# This is a helper script for EC2 deployments

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${BASE_DIR}/config/ec2-config.env"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Load configuration
if [ -f "${CONFIG_FILE}" ]; then
    source "${CONFIG_FILE}"
else
    log_warn "Config file not found, using defaults"
    MSSQL_SA_PASSWORD="ShopPass123!"
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if container already exists
CONTAINER_NAME="sqlserver-dc-shim"

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log_info "SQL Server container already exists: ${CONTAINER_NAME}"

    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "Container is already running"
        docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        exit 0
    else
        log_info "Starting existing container..."
        docker start ${CONTAINER_NAME}
        sleep 5
        log_info "SQL Server started successfully"
        exit 0
    fi
fi

# Start new container
log_info "Starting SQL Server 2022 in Docker..."
log_info "Container name: ${CONTAINER_NAME}"
log_info "Port: 1433"

docker run -d \
    --name ${CONTAINER_NAME} \
    -e 'ACCEPT_EULA=Y' \
    -e "MSSQL_SA_PASSWORD=${MSSQL_SA_PASSWORD}" \
    -e 'MSSQL_PID=Developer' \
    -p 1433:1433 \
    --restart unless-stopped \
    mcr.microsoft.com/mssql/server:2022-latest

log_info "Waiting for SQL Server to be ready..."
sleep 15

# Verify it's running
if docker ps --filter "name=${CONTAINER_NAME}" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log_info "SQL Server started successfully!"
    log_info ""
    log_info "Connection details:"
    log_info "  Server: localhost,1433"
    log_info "  Username: sa"
    log_info "  Password: ${MSSQL_SA_PASSWORD}"
    log_info ""
    log_info "To stop SQL Server:"
    log_info "  docker stop ${CONTAINER_NAME}"
    log_info ""
    log_info "To remove container:"
    log_info "  docker rm -f ${CONTAINER_NAME}"
else
    echo "Error: Failed to start SQL Server"
    docker logs ${CONTAINER_NAME}
    exit 1
fi
