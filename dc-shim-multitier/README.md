# Shop DC Shim Multi-Tier Deployment

This directory contains deployment artifacts for running the Shop DC Shim services in a multi-tier architecture. The services can be deployed in two ways:

1. **Kubernetes Deployment** - Services run as containers in a Kubernetes cluster (see `../src/shop-dc-shim/`)
2. **EC2 Deployment** - Services run as native processes on an EC2 instance (this directory)

## Overview

The Shop DC Shim simulates a datacenter-based legacy application that integrates with the modern cloud-native Astronomy Shop. It demonstrates:

- **Dual Instrumentation**: AppDynamics + Splunk Observability
- **Hybrid Architecture**: EC2-based services communicating with Kubernetes services
- **Database Integration**: SQL Server with JDBC instrumentation
- **Load Generation**: Continuous transaction generation for testing

## Components

### Services

1. **shop-dc-shim-service** - Main application service (Spring Boot)
   - Exposes REST API on port 8070
   - Connects to SQL Server database
   - Communicates with K8s checkout and email services
   - Dual instrumentation (AppDynamics + Splunk)

2. **SQL Server** - Database backend
   - Microsoft SQL Server 2022
   - Port 1433
   - Stores transaction data and audit logs

3. **Load Generator** - Python-based traffic generator
   - Generates continuous transaction load
   - Configurable TPM (Transactions Per Minute)

## Directory Structure

```
dc-shim-multitier/
├── README.md                    # This file
├── bin/                         # Executable scripts
│   ├── setup-dc-shim.sh        # Main deployment script
│   ├── stop-dc-shim.sh         # Stop all services
│   └── start-sqlserver-docker.sh # Start SQL Server via Docker
├── config/                      # Configuration files
│   └── ec2-config.env          # Environment variables (customize this!)
├── lib/                         # Application JARs
│   └── shop-dc-shim-2.1.3.jar  # Spring Boot application
├── loadgen/                     # Load generator
│   ├── shop_load_generator.py  # Python load generator
│   └── requirements.txt        # Python dependencies
├── logs/                        # Runtime logs (created at runtime)
└── docs/                        # Documentation
    ├── ec2-deployment.md       # EC2 deployment guide
    └── kubernetes-deployment.md # K8s deployment guide
```

## Quick Start (EC2 Deployment)

### Prerequisites

- Java 21 or later
- Python 3.8+ (for load generator)
- SQL Server 2022 (or Docker to run it)
- Network access to Kubernetes cluster services

### 1. Configure Environment

Edit `config/ec2-config.env` and update:

```bash
# Kubernetes cluster service endpoints
export CHECKOUT_SERVICE_ADDR="<K8S_CLUSTER_IP>:8080"
export EMAIL_SERVICE_URL="http://<K8S_CLUSTER_IP>:8080"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://<K8S_NODE_IP>:4318"

# AppDynamics credentials (if using)
export APPDYNAMICS_AGENT_ACCOUNT_ACCESS_KEY="your-token"
```

### 2. Start SQL Server

Using Docker:
```bash
./bin/start-sqlserver-docker.sh
```

Or use your existing SQL Server installation.

### 3. Deploy Services

```bash
./bin/setup-dc-shim.sh
```

This will:
- Check prerequisites (Java, Python)
- Load configuration from `config/ec2-config.env`
- Verify SQL Server connectivity
- Start shop-dc-shim service
- Start load generator (optional)

### 4. Verify Deployment

Check service health:
```bash
curl http://localhost:8070/actuator/health
```

View logs:
```bash
tail -f logs/shop-dc-shim.log
tail -f logs/loadgen.log
```

### 5. Stop Services

```bash
./bin/stop-dc-shim.sh
```

## Deployment Methods Comparison

| Aspect | Kubernetes | EC2 |
|--------|-----------|-----|
| **Deployment** | Helm/kubectl | Shell scripts |
| **Scaling** | Auto-scaling | Manual |
| **Monitoring** | K8s metrics + APM | APM only |
| **Database** | K8s pod | Docker/native |
| **Networking** | Service mesh | Direct TCP |
| **Updates** | Rolling updates | Manual restart |
| **Resource Mgmt** | Requests/limits | OS-level |
| **Use Case** | Production | Testing/demos |

## Configuration

### Environment Variables

Key configuration variables in `config/ec2-config.env`:

- `WORKSHOP_ENV` - Environment name (e.g., "ec2-test")
- `TPM` - Transactions per minute (default: 10)
- `DB_CONNECTION_STRING` - JDBC connection string
- `CHECKOUT_SERVICE_ADDR` - K8s checkout service endpoint
- `OTEL_EXPORTER_OTLP_ENDPOINT` - OpenTelemetry collector endpoint

### Agent Paths

If using APM agents, ensure they are installed:

- AppDynamics: `/opt/appdynamics/javaagent.jar`
- Splunk OTel: `/opt/splunk-otel-javaagent.jar` (or embedded)

## Networking Requirements

The EC2 instance must have network connectivity to:

1. **Kubernetes Services**:
   - `checkout:8080` (gRPC)
   - `email:8080` (HTTP)

2. **OpenTelemetry Collector**:
   - `<K8s-node-ip>:4318` (OTLP HTTP)

3. **AppDynamics Controller** (if using):
   - `se-lab.saas.appdynamics.com:443` (HTTPS)

### Accessing K8s Services from EC2

Options:

1. **NodePort Services**: Expose K8s services via NodePort
2. **LoadBalancer**: Use cloud load balancer
3. **VPN/Direct Connect**: Private network connectivity
4. **Port Forwarding**: For testing only

Example NodePort configuration:
```bash
kubectl patch svc checkout -p '{"spec":{"type":"NodePort"}}'
kubectl get svc checkout  # Note the NodePort
```

## Troubleshooting

### Service Won't Start

Check logs:
```bash
tail -f logs/shop-dc-shim.log
```

Common issues:
- SQL Server not running: `./bin/start-sqlserver-docker.sh`
- Java version < 21: `java -version`
- Incorrect K8s endpoints in config

### Can't Connect to K8s Services

Verify network connectivity:
```bash
# Test checkout service
nc -zv <K8S_IP> 8080

# Test OTEL collector
nc -zv <K8S_IP> 4318
```

### Load Generator Fails

Check Python dependencies:
```bash
cd loadgen
python3 -m pip install -r requirements.txt
```

## Documentation

- [EC2 Deployment Guide](docs/ec2-deployment.md) - Detailed EC2 setup instructions
- [Kubernetes Deployment Guide](docs/kubernetes-deployment.md) - K8s deployment reference

## Support

For issues or questions:
- GitHub Issues: https://github.com/splunk/opentelemetry-demo/issues
- Documentation: See `docs/` directory

## License

Copyright The OpenTelemetry Authors
SPDX-License-Identifier: Apache-2.0
