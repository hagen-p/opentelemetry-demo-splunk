# EC2 Deployment Guide

This guide provides detailed instructions for deploying Shop DC Shim services on an EC2 instance.

## Architecture

```
┌─────────────────────────────────────┐
│         EC2 Instance                │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  shop-dc-shim-service        │  │
│  │  (Java Spring Boot)          │  │
│  │  Port: 8070                  │  │
│  │  ┌────────────────────────┐  │  │
│  │  │ AppDynamics Agent      │  │  │
│  │  │ Splunk OTel Agent      │  │  │
│  │  └────────────────────────┘  │  │
│  └──────────────────────────────┘  │
│           ↓                         │
│  ┌──────────────────────────────┐  │
│  │  SQL Server 2022             │  │
│  │  Port: 1433                  │  │
│  └──────────────────────────────┘  │
│           ↑                         │
│  ┌──────────────────────────────┐  │
│  │  Load Generator (Python)     │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
           ↓ ↓ ↓
    Network connections to:
    - K8s checkout:8080
    - K8s email:8080
    - K8s OTEL collector:4318
    - AppDynamics SaaS
```

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+ or Amazon Linux 2)
- **CPU**: 2+ cores
- **Memory**: 4GB+ RAM
- **Disk**: 10GB+ free space
- **Network**: Access to Kubernetes cluster

### Software Requirements

1. **Java 21 or later**
   ```bash
   # Check version
   java -version

   # Install on Ubuntu
   sudo apt update
   sudo apt install openjdk-21-jdk

   # Install on Amazon Linux 2
   sudo amazon-linux-extras install java-openjdk21
   ```

2. **Python 3.8+** (for load generator)
   ```bash
   # Check version
   python3 --version

   # Install on Ubuntu
   sudo apt install python3 python3-pip

   # Install on Amazon Linux 2
   sudo yum install python3 python3-pip
   ```

3. **Docker** (optional, for SQL Server)
   ```bash
   # Install on Ubuntu
   sudo apt install docker.io
   sudo systemctl start docker
   sudo systemctl enable docker
   sudo usermod -aG docker $USER

   # Install on Amazon Linux 2
   sudo yum install docker
   sudo service docker start
   sudo usermod -aG docker ec2-user
   ```

4. **Network Tools**
   ```bash
   # Ubuntu
   sudo apt install netcat curl

   # Amazon Linux 2
   sudo yum install nc curl
   ```

## Installation

### 1. Copy Files to EC2

From your local machine:

```bash
# Create deployment package
cd /path/to/opentelemetry-demo-Splunk
tar czf dc-shim-multitier.tar.gz dc-shim-multitier/

# Copy to EC2
scp dc-shim-multitier.tar.gz ec2-user@<EC2_IP>:~/

# SSH to EC2 and extract
ssh ec2-user@<EC2_IP>
cd ~
tar xzf dc-shim-multitier.tar.gz
cd dc-shim-multitier
```

### 2. Install APM Agents (Optional)

#### AppDynamics Agent

```bash
# Download from AppDynamics portal
# Place in /opt/appdynamics/javaagent.jar

sudo mkdir -p /opt/appdynamics
# Upload your javaagent.jar
sudo cp /path/to/javaagent.jar /opt/appdynamics/
```

#### Splunk OTel Java Agent (Optional)

The shop-dc-shim JAR includes OpenTelemetry auto-instrumentation, but you can also use the standalone Splunk distribution:

```bash
# Download Splunk OTel Java agent
sudo mkdir -p /opt
curl -L https://github.com/signalfx/splunk-otel-java/releases/latest/download/splunk-otel-javaagent.jar \
  -o /opt/splunk-otel-javaagent.jar
```

## Configuration

### 1. Configure Kubernetes Access

Determine how to access your K8s services from EC2:

#### Option A: NodePort (Recommended for testing)

On your K8s cluster:

```bash
# Expose checkout service
kubectl patch svc checkout -p '{"spec":{"type":"NodePort"}}'
kubectl get svc checkout  # Note the NodePort (e.g., 30080)

# Expose email service
kubectl patch svc email -p '{"spec":{"type":"NodePort"}}'
kubectl get svc email  # Note the NodePort (e.g., 30081)

# Get node IP
kubectl get nodes -o wide  # Note EXTERNAL-IP
```

#### Option B: LoadBalancer (Production)

```bash
# Expose via LoadBalancer
kubectl patch svc checkout -p '{"spec":{"type":"LoadBalancer"}}'
kubectl get svc checkout  # Note EXTERNAL-IP

kubectl patch svc email -p '{"spec":{"type":"LoadBalancer"}}'
kubectl get svc email  # Note EXTERNAL-IP
```

#### Option C: Port Forwarding (Testing only)

```bash
# From your local machine with kubectl access
kubectl port-forward svc/checkout 8080:8080 &
kubectl port-forward svc/email 8081:8080 &

# Use local machine IP from EC2
```

### 2. Configure OTEL Collector Access

#### Option A: Use K8s Collector (via NodePort)

On your K8s cluster:

```bash
# If using Splunk OTel Collector chart
kubectl patch svc splunk-otel-collector-agent -p '{"spec":{"type":"NodePort"}}'
kubectl get svc splunk-otel-collector-agent  # Note NodePort for 4318

# Or access via Node IP (if DaemonSet)
kubectl get nodes -o wide  # Any node IP
```

#### Option B: Install Collector on EC2

```bash
# Install Splunk OTel Collector
curl -sSL https://dl.signalfx.com/splunk-otel-collector.sh > /tmp/splunk-otel-collector.sh
sudo sh /tmp/splunk-otel-collector.sh --realm <YOUR_REALM> -- <YOUR_ACCESS_TOKEN>

# Use localhost endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
```

### 3. Edit Configuration File

Edit `config/ec2-config.env`:

```bash
cd ~/dc-shim-multitier
nano config/ec2-config.env
```

Update the following variables:

```bash
# Example with NodePort
export CHECKOUT_SERVICE_ADDR="<K8S_NODE_IP>:30080"
export EMAIL_SERVICE_URL="http://<K8S_NODE_IP>:30081"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://<K8S_NODE_IP>:30318"

# Example with LoadBalancer
export CHECKOUT_SERVICE_ADDR="<CHECKOUT_LB_IP>:8080"
export EMAIL_SERVICE_URL="http://<EMAIL_LB_IP>:8080"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://<OTEL_LB_IP>:4318"

# AppDynamics (if using)
export APPDYNAMICS_AGENT_ACCOUNT_ACCESS_KEY="your-actual-token"
export APPDYNAMICS_AGENT_ACCOUNT_NAME="your-account"
export APPDYNAMICS_CONTROLLER_HOST_NAME="your-controller.saas.appdynamics.com"

# Deployment environment
export WORKSHOP_ENV="ec2-production"

# TPM (adjust load)
export TPM=20
```

### 4. Test Network Connectivity

Before deploying, verify connectivity:

```bash
# Test checkout service
nc -zv <K8S_IP> <CHECKOUT_PORT>

# Test email service
nc -zv <K8S_IP> <EMAIL_PORT>

# Test OTEL collector
nc -zv <K8S_IP> <OTEL_PORT>

# Test AppDynamics controller
nc -zv se-lab.saas.appdynamics.com 443
```

## Deployment

### 1. Start SQL Server

Using Docker:

```bash
./bin/start-sqlserver-docker.sh
```

Or if using native SQL Server:

```bash
# Verify it's running
nc -zv localhost 1433
```

### 2. Deploy Services

```bash
# Deploy with load generator
./bin/setup-dc-shim.sh

# Or deploy without load generator
./bin/setup-dc-shim.sh --no-loadgen
```

### 3. Verify Deployment

Check service health:

```bash
# Health check
curl http://localhost:8070/actuator/health

# Should return:
# {"status":"UP"}

# Check metrics endpoint
curl http://localhost:8070/actuator/metrics

# Test API endpoint
curl http://localhost:8070/api/transactions
```

### 4. Monitor Logs

```bash
# Shop DC Shim service
tail -f logs/shop-dc-shim.log

# Load generator
tail -f logs/loadgen.log

# Follow both
tail -f logs/*.log
```

## Running as a Service (systemd)

For production deployments, create a systemd service:

### Create Service File

```bash
sudo nano /etc/systemd/system/shop-dc-shim.service
```

Add:

```ini
[Unit]
Description=Shop DC Shim Service
After=network.target docker.service

[Service]
Type=forking
User=ec2-user
WorkingDirectory=/home/ec2-user/dc-shim-multitier
ExecStartPre=/home/ec2-user/dc-shim-multitier/bin/start-sqlserver-docker.sh
ExecStart=/home/ec2-user/dc-shim-multitier/bin/setup-dc-shim.sh
ExecStop=/home/ec2-user/dc-shim-multitier/bin/stop-dc-shim.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable shop-dc-shim
sudo systemctl start shop-dc-shim
sudo systemctl status shop-dc-shim
```

## Stopping Services

```bash
# Stop all services
./bin/stop-dc-shim.sh

# Stop SQL Server Docker container
docker stop sqlserver-dc-shim

# Or if using systemd
sudo systemctl stop shop-dc-shim
```

## Monitoring & Observability

### Splunk Observability

Once running, you should see:

1. **APM Traces**: Service map showing shop-dc-shim → checkout → payment
2. **Infrastructure Metrics**: If using Splunk OTel Collector on EC2
3. **Database Query Performance**: Via JDBC instrumentation
4. **Logs**: Via file collection (if configured)

Access Splunk Observability:
- APM: `https://app.<realm>.signalfx.com/#/apm`
- Infrastructure: `https://app.<realm>.signalfx.com/#/infrastructure`

### AppDynamics

If using AppDynamics:

1. **Application Dashboard**: `shop-dc-shim-service`
2. **Tier**: `shop-dc-shim`
3. **Business Transactions**: Auto-discovered API endpoints
4. **Database Calls**: SQL Server queries via JDBC exit calls

Access AppDynamics:
- Controller: `https://<your-account>.saas.appdynamics.com`

### Local Monitoring

```bash
# CPU and memory usage
top
htop  # if installed

# Check Java process
ps aux | grep shop-dc-shim

# Check open ports
netstat -tlnp | grep java

# Check connections
netstat -an | grep 8070
```

## Troubleshooting

### Service Won't Start

1. **Check Java version**:
   ```bash
   java -version
   # Must be 21+
   ```

2. **Check SQL Server**:
   ```bash
   nc -zv localhost 1433
   docker ps | grep sqlserver
   ```

3. **Check logs**:
   ```bash
   tail -f logs/shop-dc-shim.log
   ```

4. **Check configuration**:
   ```bash
   cat config/ec2-config.env | grep -v "^#" | grep -v "^$"
   ```

### Can't Connect to K8s Services

1. **Verify endpoints**:
   ```bash
   nc -zv <K8S_IP> <CHECKOUT_PORT>
   curl -v http://<K8S_IP>:<EMAIL_PORT>/health
   ```

2. **Check security groups** (AWS):
   - EC2 outbound: Allow all or specific ports
   - K8s nodes inbound: Allow from EC2 security group

3. **Check network ACLs**: Ensure subnet ACLs allow traffic

4. **Test from EC2**:
   ```bash
   telnet <K8S_IP> <PORT>
   curl -v http://<K8S_IP>:<PORT>
   ```

### High Memory Usage

1. **Reduce transaction retention**:
   Edit `config/ec2-config.env`:
   ```bash
   export TRANSACTION_RETENTION_MINUTES=15
   export AUDIT_LOG_ENABLED=false
   ```

2. **Adjust Java heap**:
   Edit `bin/setup-dc-shim.sh`, modify JAVA_OPTS:
   ```bash
   JAVA_OPTS="-Xmx512m -Xms256m"  # Reduce from default
   ```

3. **Reduce TPM**:
   ```bash
   export TPM=5  # Lower transaction rate
   ```

### Load Generator Not Working

1. **Check Python**:
   ```bash
   python3 --version
   which python3
   ```

2. **Install dependencies**:
   ```bash
   cd loadgen
   python3 -m pip install -r requirements.txt --user
   ```

3. **Check service health**:
   ```bash
   curl http://localhost:8070/actuator/health
   ```

4. **Run manually**:
   ```bash
   cd loadgen
   python3 shop_load_generator.py --url http://localhost:8070 --tpm 10
   ```

## Performance Tuning

### Optimize for High TPM

For production-like load (100+ TPM):

1. **Increase resources**:
   ```bash
   # Use larger EC2 instance (t3.large or bigger)
   # Increase Java heap
   JAVA_OPTS="-Xmx2g -Xms1g"
   ```

2. **Database tuning**:
   ```bash
   # Use dedicated SQL Server instance
   # Or increase Docker container memory
   docker run -m 4g ...
   ```

3. **Reduce retention**:
   ```bash
   export TRANSACTION_RETENTION_MINUTES=10
   export TRANSACTION_CLEANUP_INTERVAL_MS=600000  # 10 min
   ```

### Optimize for Low Resources

For minimal footprint (t3.micro):

```bash
export TPM=5
export TRANSACTION_RETENTION_MINUTES=5
export AUDIT_LOG_ENABLED=false
# Use Java heap: -Xmx512m -Xms256m
```

## Security Considerations

1. **Secrets Management**:
   - Use AWS Secrets Manager or Parameter Store for credentials
   - Don't commit `ec2-config.env` with real credentials

2. **Network Security**:
   - Use security groups to restrict access
   - Use VPC peering or PrivateLink for K8s connectivity
   - Don't expose SQL Server publicly

3. **Agent Security**:
   - Store AppDynamics token in AWS Secrets Manager
   - Use IAM roles for Splunk OTel Collector

## Next Steps

- [Kubernetes Deployment Guide](kubernetes-deployment.md)
- [Main README](../README.md)
- [OpenTelemetry Demo Documentation](https://github.com/open-telemetry/opentelemetry-demo)

## Support

For issues:
- Check logs: `tail -f logs/*.log`
- GitHub Issues: https://github.com/splunk/opentelemetry-demo/issues
