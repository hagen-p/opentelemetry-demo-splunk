#!/bin/bash
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Shop DC Shim Multi-Tier Deployment Script
# Deploys shop-dc-shim services on EC2 instance communicating with K8s cluster

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${BASE_DIR}/config/ec2-config.env"
LIB_DIR="${BASE_DIR}/lib"
LOADGEN_DIR="${BASE_DIR}/loadgen"
LOG_DIR="${BASE_DIR}/logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ==============================================================================
# Helper Functions
# ==============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check Java
    if ! command -v java &> /dev/null; then
        log_error "Java is not installed. Please install Java 21 or later."
        exit 1
    fi

    local java_version=$(java -version 2>&1 | awk -F '"' '/version/ {print $2}' | awk -F '.' '{print $1}')
    if [ "$java_version" -lt 21 ]; then
        log_error "Java version must be 21 or later. Current version: $java_version"
        exit 1
    fi
    log_info "Java version: $(java -version 2>&1 | head -n 1)"

    # Check Python (for load generator)
    if ! command -v python3 &> /dev/null; then
        log_warn "Python3 is not installed. Load generator will not be available."
    else
        log_info "Python3 version: $(python3 --version)"
    fi

    # Check if JAR file exists
    if [ ! -f "${LIB_DIR}/shop-dc-shim-2.1.3.jar" ]; then
        log_error "shop-dc-shim JAR file not found in ${LIB_DIR}"
        exit 1
    fi

    log_info "Prerequisites check passed."
}

load_configuration() {
    log_info "Loading configuration from ${CONFIG_FILE}..."

    if [ ! -f "${CONFIG_FILE}" ]; then
        log_error "Configuration file not found: ${CONFIG_FILE}"
        log_error "Please copy and customize config/ec2-config.env"
        exit 1
    fi

    source "${CONFIG_FILE}"

    # Validate required variables
    if [[ "${CHECKOUT_SERVICE_ADDR}" == *"K8S_CLUSTER_IP"* ]]; then
        log_error "CHECKOUT_SERVICE_ADDR not configured. Please update ${CONFIG_FILE}"
        exit 1
    fi

    if [[ "${OTEL_EXPORTER_OTLP_ENDPOINT}" == *"K8S_NODE_IP"* ]]; then
        log_error "OTEL_EXPORTER_OTLP_ENDPOINT not configured. Please update ${CONFIG_FILE}"
        exit 1
    fi

    log_info "Configuration loaded successfully."
}

setup_logging() {
    mkdir -p "${LOG_DIR}"
    log_info "Log directory: ${LOG_DIR}"
}

check_sql_server() {
    log_info "Checking SQL Server availability..."

    # Check if SQL Server is running on localhost:1433
    if nc -z localhost 1433 2>/dev/null; then
        log_info "SQL Server is already running on localhost:1433"
        return 0
    else
        log_warn "SQL Server is not running on localhost:1433"
        log_warn "Please start SQL Server manually or using Docker:"
        log_warn "  docker run -e 'ACCEPT_EULA=Y' -e 'MSSQL_SA_PASSWORD=ShopPass123!' \\"
        log_warn "    -p 1433:1433 --name sqlserver -d mcr.microsoft.com/mssql/server:2022-latest"
        return 1
    fi
}

start_shop_dc_shim() {
    log_info "Starting Shop DC Shim Service..."

    # Check if agents are available
    local AGENT_ARGS=""

    if [ -f "${APPDYNAMICS_AGENT_PATH}" ]; then
        log_info "AppDynamics agent found: ${APPDYNAMICS_AGENT_PATH}"
        AGENT_ARGS="-javaagent:${APPDYNAMICS_AGENT_PATH}"
        AGENT_ARGS="${AGENT_ARGS} -Dagent.deployment.mode=dual"
        AGENT_ARGS="${AGENT_ARGS} -Dappdynamics.sim.enabled=true"
    else
        log_warn "AppDynamics agent not found at ${APPDYNAMICS_AGENT_PATH}"
        log_warn "Running without AppDynamics instrumentation"
    fi

    # Build Java command
    local JAVA_OPTS="-Xmx1g -Xms512m"
    JAVA_OPTS="${JAVA_OPTS} -Dotel.instrumentation.jdbc.enabled=true"
    JAVA_OPTS="${JAVA_OPTS} -Dotel.resource.attributes=${OTEL_RESOURCE_ATTRIBUTES}"
    JAVA_OPTS="${JAVA_OPTS} -Dsplunk.profiler.enabled=true"
    JAVA_OPTS="${JAVA_OPTS} -Dsplunk.profiler.memory.enabled=true"
    JAVA_OPTS="${JAVA_OPTS} -Dsplunk.snapshot.profiler.enabled=true"
    JAVA_OPTS="${JAVA_OPTS} -Dsplunk.snapshot.selection.probability=0.2"
    JAVA_OPTS="${JAVA_OPTS} -Dotel.exporter.otlp.endpoint=${OTEL_EXPORTER_OTLP_ENDPOINT}"

    log_info "Configuration:"
    log_info "  Service: shop-dc-shim-service"
    log_info "  Port: ${SHOP_DC_SHIM_PORT}"
    log_info "  Database: ${DB_CONNECTION_STRING}"
    log_info "  Checkout Service: ${CHECKOUT_SERVICE_ADDR}"
    log_info "  Email Service: ${EMAIL_SERVICE_URL}"
    log_info "  OTEL Endpoint: ${OTEL_EXPORTER_OTLP_ENDPOINT}"
    log_info "  OTEL Resource Attributes: ${OTEL_RESOURCE_ATTRIBUTES}"

    if [ -n "${AGENT_ARGS}" ]; then
        log_info "  AppDynamics Application: ${APPDYNAMICS_AGENT_APPLICATION_NAME}"
        log_info "  AppDynamics Controller: ${APPDYNAMICS_CONTROLLER_HOST_NAME}"
    fi

    # Start the service in background
    nohup java ${AGENT_ARGS} ${JAVA_OPTS} \
        -jar "${LIB_DIR}/shop-dc-shim-2.1.3.jar" \
        > "${LOG_DIR}/shop-dc-shim.log" 2>&1 &

    local PID=$!
    echo $PID > "${LOG_DIR}/shop-dc-shim.pid"

    log_info "Shop DC Shim Service started with PID: $PID"
    log_info "Logs: ${LOG_DIR}/shop-dc-shim.log"

    # Wait for service to start
    log_info "Waiting for service to be ready..."
    local max_attempts=60
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s http://localhost:${SHOP_DC_SHIM_PORT}/actuator/health > /dev/null 2>&1; then
            log_info "Service is ready!"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    log_error "Service did not become ready within expected time"
    log_error "Check logs: tail -f ${LOG_DIR}/shop-dc-shim.log"
    return 1
}

start_load_generator() {
    log_info "Starting Load Generator..."

    if ! command -v python3 &> /dev/null; then
        log_warn "Python3 not found. Skipping load generator."
        return 1
    fi

    # Install dependencies
    if [ -f "${LOADGEN_DIR}/requirements.txt" ]; then
        log_info "Installing Python dependencies..."
        python3 -m pip install -q -r "${LOADGEN_DIR}/requirements.txt"
    fi

    # Check if shop-dc-shim is ready
    if ! curl -s http://localhost:${SHOP_DC_SHIM_PORT}/actuator/health > /dev/null 2>&1; then
        log_warn "Shop DC Shim service is not ready. Skipping load generator."
        return 1
    fi

    # Start load generator
    cd "${LOADGEN_DIR}"
    nohup python3 shop_load_generator.py \
        --url "http://localhost:${SHOP_DC_SHIM_PORT}" \
        --tpm "${LOAD_GENERATOR_TPM}" \
        > "${LOG_DIR}/loadgen.log" 2>&1 &

    local PID=$!
    echo $PID > "${LOG_DIR}/loadgen.pid"

    log_info "Load Generator started with PID: $PID"
    log_info "Logs: ${LOG_DIR}/loadgen.log"
    log_info "TPM: ${LOAD_GENERATOR_TPM}"
}

show_status() {
    log_info ""
    log_info "========================================="
    log_info "DC Shim Deployment Status"
    log_info "========================================="

    # Check shop-dc-shim
    if [ -f "${LOG_DIR}/shop-dc-shim.pid" ]; then
        local PID=$(cat "${LOG_DIR}/shop-dc-shim.pid")
        if ps -p $PID > /dev/null 2>&1; then
            log_info "✓ Shop DC Shim Service (PID: $PID) - Running"
            log_info "  URL: http://localhost:${SHOP_DC_SHIM_PORT}"
            log_info "  Health: http://localhost:${SHOP_DC_SHIM_PORT}/actuator/health"
        else
            log_warn "✗ Shop DC Shim Service - Not running (stale PID)"
        fi
    else
        log_warn "✗ Shop DC Shim Service - Not started"
    fi

    # Check load generator
    if [ -f "${LOG_DIR}/loadgen.pid" ]; then
        local PID=$(cat "${LOG_DIR}/loadgen.pid")
        if ps -p $PID > /dev/null 2>&1; then
            log_info "✓ Load Generator (PID: $PID) - Running"
        else
            log_warn "✗ Load Generator - Not running (stale PID)"
        fi
    else
        log_warn "✗ Load Generator - Not started"
    fi

    log_info "========================================="
    log_info ""
    log_info "To stop services, run:"
    log_info "  ${SCRIPT_DIR}/stop-dc-shim.sh"
    log_info ""
    log_info "To view logs:"
    log_info "  tail -f ${LOG_DIR}/shop-dc-shim.log"
    log_info "  tail -f ${LOG_DIR}/loadgen.log"
}

# ==============================================================================
# Main
# ==============================================================================

main() {
    log_info "========================================="
    log_info "Shop DC Shim Multi-Tier Deployment"
    log_info "========================================="
    log_info ""

    check_prerequisites
    load_configuration
    setup_logging

    # Check SQL Server
    if ! check_sql_server; then
        log_error "SQL Server is required. Please start SQL Server and try again."
        exit 1
    fi

    # Start services
    start_shop_dc_shim

    # Start load generator (optional)
    if [ "${1}" != "--no-loadgen" ]; then
        sleep 5  # Give shop-dc-shim a bit more time
        start_load_generator || log_warn "Load generator failed to start (non-critical)"
    fi

    # Show status
    show_status
}

# Run main function
main "$@"
