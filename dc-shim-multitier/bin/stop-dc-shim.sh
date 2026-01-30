#!/bin/bash
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Stop DC Shim Services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${BASE_DIR}/logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

stop_service() {
    local service_name=$1
    local pid_file="${LOG_DIR}/${service_name}.pid"

    if [ ! -f "$pid_file" ]; then
        log_warn "${service_name} - No PID file found"
        return 1
    fi

    local PID=$(cat "$pid_file")

    if ! ps -p $PID > /dev/null 2>&1; then
        log_warn "${service_name} - Process not running (PID: $PID)"
        rm -f "$pid_file"
        return 1
    fi

    log_info "Stopping ${service_name} (PID: $PID)..."
    kill $PID

    # Wait for process to stop
    local max_wait=30
    local count=0
    while ps -p $PID > /dev/null 2>&1 && [ $count -lt $max_wait ]; do
        sleep 1
        count=$((count + 1))
    done

    if ps -p $PID > /dev/null 2>&1; then
        log_warn "${service_name} did not stop gracefully, forcing..."
        kill -9 $PID
        sleep 1
    fi

    rm -f "$pid_file"
    log_info "${service_name} stopped successfully"
    return 0
}

main() {
    log_info "========================================="
    log_info "Stopping DC Shim Services"
    log_info "========================================="
    log_info ""

    if [ ! -d "$LOG_DIR" ]; then
        log_warn "Log directory not found. No services appear to be running."
        exit 0
    fi

    # Stop load generator first
    stop_service "loadgen" || true

    # Stop shop-dc-shim
    stop_service "shop-dc-shim" || true

    log_info ""
    log_info "All services stopped."
}

main "$@"
