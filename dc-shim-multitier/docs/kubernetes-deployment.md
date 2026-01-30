# Kubernetes Deployment Guide

This guide documents the Kubernetes deployment method for Shop DC Shim services. This is the primary deployment method for production environments.

## Architecture

```
┌──────────────────────────────────────────────────┐
│            Kubernetes Cluster                     │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │  shop-dc-shim Deployment                    │ │
│  │  ┌───────────────────────────────────────┐  │ │
│  │  │  Pod: shop-dc-shim                    │  │ │
│  │  │  ┌─────────────────────────────────┐  │  │ │
│  │  │  │  Container: shop-dc-shim        │  │  │ │
│  │  │  │  - Java Spring Boot app         │  │  │ │
│  │  │  │  - Port 8070                    │  │  │ │
│  │  │  │  - AppDynamics agent            │  │  │ │
│  │  │  │  - Splunk OTel instrumentation  │  │  │ │
│  │  │  └─────────────────────────────────┘  │  │ │
│  │  └───────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────┘ │
│                     ↓                             │
│  ┌─────────────────────────────────────────────┐ │
│  │  shop-dc-shim-db StatefulSet                │ │
│  │  ┌───────────────────────────────────────┐  │ │
│  │  │  Pod: shop-dc-shim-db                 │  │ │
│  │  │  - SQL Server 2022                    │  │ │
│  │  │  - Port 1433                          │  │ │
│  │  │  - PersistentVolume                   │  │ │
│  │  └───────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────┘ │
│                     ↑                             │
│  ┌─────────────────────────────────────────────┐ │
│  │  shop-dc-loadgenerator Deployment          │ │
│  │  ┌───────────────────────────────────────┐  │ │
│  │  │  Pod: shop-dc-loadgenerator           │  │ │
│  │  │  - Python load generator              │  │ │
│  │  │  - Generates traffic to shop-dc-shim  │  │ │
│  │  └───────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  Connected to other services:                    │
│  - checkout:8080 (gRPC)                          │
│  - email:8080 (HTTP)                             │
│  - splunk-otel-collector-agent:4318 (OTLP)      │
└──────────────────────────────────────────────────┘
```

## Prerequisites

### Kubernetes Cluster

- Kubernetes 1.24+
- kubectl configured with cluster access
- Sufficient cluster resources:
  - CPU: 2+ cores available
  - Memory: 4GB+ available
  - Storage: 10GB+ for SQL Server PV

### Required Services

The following services must be deployed in the same cluster:

1. **Astronomy Shop Demo** (or compatible services):
   - `checkout` service (port 8080)
   - `email` service (port 8080)

2. **Splunk OpenTelemetry Collector**:
   - Deployed as DaemonSet or Deployment
   - OTLP receiver on port 4318

### Required Secrets

Create the `workshop-secret` secret with AppDynamics credentials:

```bash
kubectl create secret generic workshop-secret \
  --from-literal=appd_token=your-appdynamics-token \
  --from-literal=env=your-environment-name \
  -n default
```

## Deployment Files

The Kubernetes manifests are located in `../src/`:

- `shop-dc-shim/shop-dc-shim-k8s.yaml` - Main application deployment
- `shop-dc-shim-db/shop-dc-shim-db-k8s.yaml` - SQL Server database
- `shop-dc-loadgenerator/shop-dc-loadgenerator-k8s.yaml` - Load generator

## Deployment Steps

### 1. Review Configuration

Edit `src/shop-dc-shim/shop-dc-shim-k8s.yaml` if needed:

```yaml
# Key configuration options:
env:
  - name: TPM
    value: "10"  # Transactions Per Minute
  - name: TRANSACTION_RETENTION_MINUTES
    value: "30"  # Transaction retention time
  - name: TRANSACTION_CLEANUP_INTERVAL_MS
    value: "1800000"  # Cleanup interval (30 min)
```

### 2. Deploy SQL Server Database

```bash
kubectl apply -f src/shop-dc-shim-db/shop-dc-shim-db-k8s.yaml
```

Verify deployment:

```bash
# Check pod status
kubectl get pod -l app.kubernetes.io/name=shop-dc-shim-db

# Check logs
kubectl logs -l app.kubernetes.io/name=shop-dc-shim-db --tail=50

# Verify service
kubectl get svc shop-dc-shim-db
```

### 3. Deploy Shop DC Shim Service

```bash
kubectl apply -f src/shop-dc-shim/shop-dc-shim-k8s.yaml
```

Verify deployment:

```bash
# Check pod status
kubectl get pod -l app.kubernetes.io/name=shop-dc-shim

# Check logs (may take 3-4 minutes to start)
kubectl logs -l app.kubernetes.io/name=shop-dc-shim --tail=100 -f

# Wait for readiness
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=shop-dc-shim --timeout=300s

# Check health endpoint
kubectl port-forward svc/shop-dc-shim 8070:8070 &
curl http://localhost:8070/actuator/health
```

Expected output:
```json
{"status":"UP"}
```

### 4. Deploy Load Generator (Optional)

```bash
kubectl apply -f src/shop-dc-loadgenerator/shop-dc-loadgenerator-k8s.yaml
```

Verify:

```bash
kubectl get pod -l app.kubernetes.io/name=shop-dc-loadgenerator
kubectl logs -l app.kubernetes.io/name=shop-dc-loadgenerator --tail=50 -f
```

## Configuration Options

### Environment Variables

Key environment variables in the deployment:

```yaml
# Service Configuration
- name: SHOP_DC_SHIM_PORT
  value: "8070"

# Database Configuration
- name: DB_CONNECTION_STRING
  value: "jdbc:sqlserver://shop-dc-shim-db:1433;databaseName=master;encrypt=false;trustServerCertificate=true"
- name: DB_USERNAME
  value: "sa"
- name: DB_PASSWORD
  value: "ShopPass123!"

# Kubernetes Service Endpoints
- name: CHECKOUT_SERVICE_ADDR
  value: "checkout:8080"
- name: EMAIL_SERVICE_URL
  value: "http://email:8080"

# OpenTelemetry Configuration
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: "http://splunk-otel-collector-agent:4318"
- name: OTEL_SERVICE_NAME
  value: "shop-dc-shim"
- name: OTEL_INSTRUMENTATION_SPLUNK_JDBC_ENABLED
  value: "true"

# AppDynamics Configuration
- name: APPDYNAMICS_AGENT_ACCOUNT_NAME
  value: "se-lab"
- name: APPDYNAMICS_JAVAAGENT_ENABLED
  value: "true"
- name: APPDYNAMICS_AGENT_ACCOUNT_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: workshop-secret
      key: appd_token

# Workshop Environment (from secret)
- name: WORKSHOP_ENV
  valueFrom:
    secretKeyRef:
      name: workshop-secret
      key: env
```

### Resource Limits

Default resource configuration:

```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "1Gi"
    cpu: "1"
```

For higher load, increase resources:

```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "1"
  limits:
    memory: "2Gi"
    cpu: "2"
```

### Probes

Readiness and liveness probes are configured with conservative timeouts:

```yaml
readinessProbe:
  httpGet:
    path: /actuator/health
    port: 8070
  initialDelaySeconds: 240  # 4 minutes
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /actuator/health
    port: 8070
  initialDelaySeconds: 420  # 7 minutes
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 5
```

## Scaling

### Manual Scaling

Scale the shop-dc-shim deployment:

```bash
# Scale up
kubectl scale deployment shop-dc-shim --replicas=3

# Scale down
kubectl scale deployment shop-dc-shim --replicas=1

# Check status
kubectl get deployment shop-dc-shim
```

### Auto-Scaling (HPA)

Create Horizontal Pod Autoscaler:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: shop-dc-shim-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: shop-dc-shim
  minReplicas: 1
  maxReplicas: 5
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

Apply:

```bash
kubectl apply -f shop-dc-shim-hpa.yaml
kubectl get hpa shop-dc-shim-hpa --watch
```

## Updating the Deployment

### Update Configuration

```bash
# Edit deployment
kubectl edit deployment shop-dc-shim

# Or apply updated manifest
kubectl apply -f src/shop-dc-shim/shop-dc-shim-k8s.yaml
```

### Update Image

```bash
# Update to new image version
kubectl set image deployment/shop-dc-shim \
  shop-dc-shim=ghcr.io/splunk/opentelemetry-demo/otel-shop-dc-shim:1.6.0

# Watch rollout
kubectl rollout status deployment/shop-dc-shim

# Check history
kubectl rollout history deployment/shop-dc-shim
```

### Rollback

```bash
# Rollback to previous version
kubectl rollout undo deployment/shop-dc-shim

# Rollback to specific revision
kubectl rollout undo deployment/shop-dc-shim --to-revision=2
```

## Monitoring

### Pod Status

```bash
# List all DC shim pods
kubectl get pods -l app.kubernetes.io/part-of=opentelemetry-demo | grep dc

# Describe pod
kubectl describe pod <pod-name>

# Get events
kubectl get events --sort-by='.lastTimestamp' | grep shop-dc
```

### Logs

```bash
# Follow logs
kubectl logs -f deployment/shop-dc-shim

# Logs from all replicas
kubectl logs -f -l app.kubernetes.io/name=shop-dc-shim --all-containers=true

# Previous pod logs (after crash)
kubectl logs deployment/shop-dc-shim --previous

# Logs with timestamps
kubectl logs deployment/shop-dc-shim --timestamps
```

### Metrics

```bash
# Pod resource usage
kubectl top pod -l app.kubernetes.io/name=shop-dc-shim

# Node resource usage
kubectl top nodes
```

### Health Checks

```bash
# Port forward to service
kubectl port-forward svc/shop-dc-shim 8070:8070

# Check health
curl http://localhost:8070/actuator/health

# Check metrics
curl http://localhost:8070/actuator/metrics

# Check info
curl http://localhost:8070/actuator/info
```

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl get pod -l app.kubernetes.io/name=shop-dc-shim

# Describe pod for events
kubectl describe pod <pod-name>

# Check logs
kubectl logs <pod-name> --tail=100

# Common issues:
# 1. Secret not found - verify workshop-secret exists
# 2. ImagePullBackOff - check image name and registry access
# 3. CrashLoopBackOff - check logs for application errors
```

### Database Connection Issues

```bash
# Check SQL Server pod
kubectl get pod -l app.kubernetes.io/name=shop-dc-shim-db

# Test connectivity from shop-dc-shim pod
kubectl exec -it <shop-dc-shim-pod> -- nc -zv shop-dc-shim-db 1433

# Check SQL Server logs
kubectl logs <shop-dc-shim-db-pod>
```

### Can't Connect to Checkout/Email Services

```bash
# Verify services exist
kubectl get svc checkout email

# Test connectivity
kubectl exec -it <shop-dc-shim-pod> -- nc -zv checkout 8080
kubectl exec -it <shop-dc-shim-pod> -- nc -zv email 8080

# Check if astronomy shop is deployed
kubectl get deployment checkout email
```

### High Memory Usage

```bash
# Check current usage
kubectl top pod -l app.kubernetes.io/name=shop-dc-shim

# Reduce transaction retention
kubectl set env deployment/shop-dc-shim \
  TRANSACTION_RETENTION_MINUTES=15 \
  AUDIT_LOG_ENABLED=false

# Or increase memory limit
kubectl set resources deployment/shop-dc-shim \
  --limits=memory=2Gi \
  --requests=memory=1Gi
```

### Restart Issues (CrashLoopBackOff)

```bash
# Get pod restarts count
kubectl get pods -l app.kubernetes.io/name=shop-dc-shim

# Check OOMKilled events
kubectl get events --field-selector involvedObject.name=<pod-name> | grep OOM

# Increase memory if OOMKilled
kubectl set resources deployment/shop-dc-shim \
  --limits=memory=2Gi \
  --requests=memory=1Gi
```

## Network Policies

If using network policies, ensure traffic is allowed:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: shop-dc-shim-policy
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: shop-dc-shim
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app.kubernetes.io/name: shop-dc-loadgenerator
    ports:
    - protocol: TCP
      port: 8070
  egress:
  # Allow DNS
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: UDP
      port: 53
  # Allow SQL Server
  - to:
    - podSelector:
        matchLabels:
          app.kubernetes.io/name: shop-dc-shim-db
    ports:
    - protocol: TCP
      port: 1433
  # Allow checkout service
  - to:
    - podSelector:
        matchLabels:
          app.kubernetes.io/name: checkout
    ports:
    - protocol: TCP
      port: 8080
  # Allow email service
  - to:
    - podSelector:
        matchLabels:
          app.kubernetes.io/name: email
    ports:
    - protocol: TCP
      port: 8080
  # Allow OTEL collector
  - to:
    - podSelector:
        matchLabels:
          app: splunk-otel-collector
    ports:
    - protocol: TCP
      port: 4318
  # Allow AppDynamics SaaS
  - to:
    - podSelector: {}
    ports:
    - protocol: TCP
      port: 443
```

## Cleanup

Remove all DC shim components:

```bash
# Delete deployments
kubectl delete -f src/shop-dc-loadgenerator/shop-dc-loadgenerator-k8s.yaml
kubectl delete -f src/shop-dc-shim/shop-dc-shim-k8s.yaml
kubectl delete -f src/shop-dc-shim-db/shop-dc-shim-db-k8s.yaml

# Or by label
kubectl delete all -l app.kubernetes.io/part-of=opentelemetry-demo,app.kubernetes.io/component=shop-dc-shim
kubectl delete all -l app.kubernetes.io/part-of=opentelemetry-demo,app.kubernetes.io/component=shop-dc-shim-db
kubectl delete all -l app.kubernetes.io/part-of=opentelemetry-demo,app.kubernetes.io/component=shop-dc-loadgenerator

# Delete PVCs (if applicable)
kubectl delete pvc -l app.kubernetes.io/name=shop-dc-shim-db
```

## Next Steps

- [EC2 Deployment Guide](ec2-deployment.md) - Alternative deployment on EC2
- [Main README](../README.md) - Overview and comparison

## Support

- GitHub Issues: https://github.com/splunk/opentelemetry-demo/issues
- OpenTelemetry Demo: https://github.com/open-telemetry/opentelemetry-demo
