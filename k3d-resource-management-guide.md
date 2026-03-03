# K3d Resource Management & Cleanup Best Practices

**Environment**: k3d (K3s in Docker containers)
**Challenge**: Balance giving k3d adequate resources while preventing resource exhaustion

## Understanding K3d Architecture

K3d runs Kubernetes (K3s) inside Docker containers:
- **Server nodes**: Run the control plane (API server, scheduler, etcd)
- **Agent nodes**: Run workloads (your pods)
- Each node is a Docker container with its own volume

**Key Issue**: Resources accumulate inside these containers (images, logs, temporary files) and can't be easily cleaned from the host.

---

## Part 1: Resource Allocation Strategies

### 1.1 K3d Cluster Creation with Resource Limits

When creating/recreating your k3d cluster, configure resource limits:

```bash
k3d cluster create astronomy-shop-us-cluster \
  # Server node configuration
  --servers 1 \
  --servers-memory "4g" \
  \
  # Agent node configuration
  --agents 2 \
  --agents-memory "8g" \
  \
  # Volume configuration
  --volume /var/lib/rancher/k3s/storage:/var/lib/rancher/k3s/storage@all \
  \
  # Port mappings for your services
  --port "8080:80@loadbalancer" \
  --port "8443:443@loadbalancer" \
  \
  # Image handling
  --registry-create k3d-registry.localhost:5000 \
  \
  # Kubelet configuration for resource management
  --k3s-arg "--kubelet-arg=image-gc-high-threshold=85@server:*" \
  --k3s-arg "--kubelet-arg=image-gc-low-threshold=80@agent:*" \
  --k3s-arg "--kubelet-arg=image-gc-high-threshold=85@agent:*" \
  --k3s-arg "--kubelet-arg=image-gc-low-threshold=80@agent:*" \
  \
  # Log rotation (from Solution 4)
  --k3s-arg "--kubelet-arg=container-log-max-size=10Mi@server:*" \
  --k3s-arg "--kubelet-arg=container-log-max-files=5@server:*" \
  --k3s-arg "--kubelet-arg=container-log-max-size=10Mi@agent:*" \
  --k3s-arg "--kubelet-arg=container-log-max-files=5@agent:*" \
  \
  # Eviction thresholds to prevent node overload
  --k3s-arg "--kubelet-arg=eviction-hard=memory.available<1Gi@server:*" \
  --k3s-arg "--kubelet-arg=eviction-hard=nodefs.available<10%@server:*" \
  --k3s-arg "--kubelet-arg=eviction-hard=memory.available<1Gi@agent:*" \
  --k3s-arg "--kubelet-arg=eviction-hard=nodefs.available<10%@agent:*" \
  \
  # Soft eviction with grace periods
  --k3s-arg "--kubelet-arg=eviction-soft=memory.available<2Gi@agent:*" \
  --k3s-arg "--kubelet-arg=eviction-soft=nodefs.available<15%@agent:*" \
  --k3s-arg "--kubelet-arg=eviction-soft-grace-period=memory.available=2m@agent:*" \
  --k3s-arg "--kubelet-arg=eviction-soft-grace-period=nodefs.available=2m@agent:*"
```

### 1.2 Docker Daemon Configuration

Configure Docker to manage resources for all containers (including k3d):

```bash
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 64000,
      "Soft": 64000
    }
  },
  "max-concurrent-downloads": 3,
  "max-concurrent-uploads": 5
}
EOF

sudo systemctl restart docker
```

### 1.3 Kubernetes Resource Quotas per Namespace

Set resource limits for your workloads to prevent any single service from consuming all resources:

```yaml
# resource-quota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: default-quota
  namespace: default
spec:
  hard:
    requests.cpu: "20"
    requests.memory: 32Gi
    limits.cpu: "40"
    limits.memory: 64Gi
    persistentvolumeclaims: "10"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limit-range
  namespace: default
spec:
  limits:
  - max:
      cpu: "4"
      memory: 8Gi
    min:
      cpu: "50m"
      memory: 64Mi
    default:
      cpu: "500m"
      memory: 512Mi
    defaultRequest:
      cpu: "100m"
      memory: 128Mi
    type: Container
```

Apply with:
```bash
kubectl apply -f resource-quota.yaml
```

---

## Part 2: Automated Cleanup Strategies

### 2.1 K3s Image Garbage Collection Configuration

K3s has built-in image garbage collection. Configure it in your k3d cluster:

```bash
# Already included in cluster creation above, but here's what it does:
# --kubelet-arg=image-gc-high-threshold=85  # Start GC when disk usage > 85%
# --kubelet-arg=image-gc-low-threshold=80   # Stop GC when disk usage < 80%
```

This automatically removes:
- Unused container images
- Old image layers
- Dangling images

### 2.2 Containerd Configuration for K3d

Configure containerd (used by k3s) to be more aggressive with cleanup:

```bash
# Create a k3d config file
cat > k3d-config.yaml <<'EOF'
apiVersion: k3d.io/v1alpha5
kind: Simple
metadata:
  name: astronomy-shop-us-cluster
servers: 1
agents: 2
options:
  k3s:
    extraArgs:
      - arg: --kubelet-arg=image-gc-high-threshold=85
        nodeFilters:
          - all
      - arg: --kubelet-arg=image-gc-low-threshold=80
        nodeFilters:
          - all
      - arg: --kubelet-arg=eviction-hard=imagefs.available<15%
        nodeFilters:
          - all
      - arg: --kubelet-arg=eviction-minimum-reclaim=imagefs.available=2Gi
        nodeFilters:
          - all
EOF

# Use this config when creating cluster
k3d cluster create --config k3d-config.yaml
```

### 2.3 Automated K3d-Specific Cleanup Script

Create a comprehensive cleanup script that handles k3d internals:

```bash
sudo tee /usr/local/bin/k3d-cleanup.sh <<'EOF'
#!/bin/bash
# K3d Cluster Cleanup Script

LOG_FILE="/var/log/k3d-cleanup.log"
echo "=== K3d Cleanup Started: $(date) ===" >> $LOG_FILE

# 1. Clean up Docker system (host level)
echo "Cleaning Docker system..." >> $LOG_FILE
docker system prune -f --volumes --filter "until=72h" >> $LOG_FILE 2>&1

# 2. Clean up images inside k3d containers
echo "Cleaning images in k3d nodes..." >> $LOG_FILE
for container in $(docker ps --filter "name=k3d" --format "{{.Names}}"); do
    echo "Processing $container..." >> $LOG_FILE

    # Use crictl (containerd CLI) inside k3d containers
    docker exec $container sh -c "
        # Remove unused images
        crictl rmi --prune 2>&1

        # Remove stopped containers
        crictl rm \$(crictl ps -a -q --state=exited 2>/dev/null) 2>&1 || true

        # Clean up unused pods
        crictl rmp \$(crictl pods -q --state=NotReady 2>/dev/null) 2>&1 || true
    " >> $LOG_FILE 2>&1
done

# 3. Kubernetes cleanup
echo "Cleaning Kubernetes resources..." >> $LOG_FILE
# Remove completed jobs older than 1 day
kubectl delete jobs --field-selector status.successful=1 -A >> $LOG_FILE 2>&1

# Remove failed pods older than 1 day
kubectl delete pods --field-selector status.phase=Failed -A >> $LOG_FILE 2>&1

# Remove evicted pods
kubectl get pods -A | grep Evicted | awk '{print $2, $1}' | xargs -n2 sh -c 'kubectl delete pod $0 -n $1' >> $LOG_FILE 2>&1 || true

# 4. Check and log disk usage
echo "Current disk usage:" >> $LOG_FILE
df -h / >> $LOG_FILE 2>&1
docker system df >> $LOG_FILE 2>&1

echo "=== K3d Cleanup Completed: $(date) ===" >> $LOG_FILE
echo "" >> $LOG_FILE
EOF

sudo chmod +x /usr/local/bin/k3d-cleanup.sh
```

### 2.4 Automated Cleanup Cron Job

Schedule the cleanup script to run automatically:

```bash
sudo tee /etc/cron.d/k3d-cleanup <<'EOF'
# K3d cleanup - Runs every Sunday at 2 AM
0 2 * * 0 root /usr/local/bin/k3d-cleanup.sh

# Quick cleanup (less aggressive) - Runs daily at 3 AM
0 3 * * * root /usr/bin/docker system prune -f >> /var/log/docker-daily-cleanup.log 2>&1
EOF
```

### 2.5 Pod Disruption Budget (Prevent Eviction Issues)

Protect critical services during cleanup and resource pressure:

```yaml
# pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: frontend-pdb
  namespace: default
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: frontend
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: payment-pdb
  namespace: default
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: payment
---
# Add PDBs for all critical services
```

Apply with:
```bash
kubectl apply -f pdb.yaml
```

---

## Part 3: Monitoring & Alerting

### 3.1 Disk Usage Monitoring Script

Create a monitoring script that alerts before problems occur:

```bash
sudo tee /usr/local/bin/check-k3d-resources.sh <<'EOF'
#!/bin/bash

ALERT_THRESHOLD=75
CRITICAL_THRESHOLD=85

# Check host disk usage
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

if [ $DISK_USAGE -ge $CRITICAL_THRESHOLD ]; then
    echo "CRITICAL: Disk usage at ${DISK_USAGE}% on astronomy-shop-us"
    # Send alert (configure your alerting here)
    # curl -X POST your-slack-webhook -d "Disk usage critical: ${DISK_USAGE}%"
elif [ $DISK_USAGE -ge $ALERT_THRESHOLD ]; then
    echo "WARNING: Disk usage at ${DISK_USAGE}% on astronomy-shop-us"
fi

# Check Docker disk usage
echo "Docker system usage:"
docker system df

# Check k3d container sizes
echo -e "\nK3d container sizes:"
for container in $(docker ps --filter "name=k3d" --format "{{.Names}}"); do
    SIZE=$(docker exec $container du -sh /var/lib/rancher/k3s 2>/dev/null | awk '{print $1}')
    echo "$container: $SIZE"
done

# Check Kubernetes node resources
echo -e "\nKubernetes node resources:"
kubectl top nodes 2>/dev/null || echo "Metrics server not available"

# Check for pods in bad states
echo -e "\nPods in non-running states:"
kubectl get pods -A | grep -v Running | grep -v Completed
EOF

sudo chmod +x /usr/local/bin/check-k3d-resources.sh
```

Schedule regular checks:
```bash
sudo tee -a /etc/cron.d/k3d-cleanup <<'EOF'
# Resource monitoring - Runs every 6 hours
0 */6 * * * root /usr/local/bin/check-k3d-resources.sh >> /var/log/k3d-monitoring.log 2>&1
EOF
```

### 3.2 Kubernetes Metrics Server (Optional but Recommended)

Install metrics-server for resource monitoring:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Patch for k3d (metrics-server needs insecure TLS for k3d)
kubectl patch deployment metrics-server -n kube-system --type='json' -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/containers/0/args/-",
    "value": "--kubelet-insecure-tls"
  }
]'
```

Now you can use:
```bash
kubectl top nodes
kubectl top pods -A
```

---

## Part 4: Application-Level Best Practices

### 4.1 Set Resource Requests and Limits on All Pods

Example for your astronomy shop services:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  template:
    spec:
      containers:
      - name: frontend
        image: frontend:latest
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
```

**Why this matters in k3d**:
- Prevents any pod from consuming all node resources
- Allows Kubernetes to make better scheduling decisions
- Enables eviction policies to work correctly

### 4.2 Use Image Pull Policies Wisely

```yaml
containers:
- name: myapp
  image: myapp:v1.0.0
  imagePullPolicy: IfNotPresent  # Don't pull if image exists locally
```

**Options**:
- `Always`: Always pull (accumulates old versions)
- `IfNotPresent`: Only pull if not cached (recommended for k3d)
- `Never`: Never pull (use for images you build locally)

### 4.3 Implement Horizontal Pod Autoscaling

Let Kubernetes manage replicas based on load:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: frontend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: frontend
  minReplicas: 2
  maxReplicas: 10
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

---

## Part 5: Emergency Response Procedures

### When Disk is Almost Full (>90%)

```bash
# 1. Immediate: Truncate large log files
ssh astronomy-shop-us 'sudo find /var/lib/docker/containers -name "*-json.log" -type f -size +100M -exec truncate -s 0 {} \;'

# 2. Force Docker cleanup
ssh astronomy-shop-us "sudo docker system prune -a -f --volumes"

# 3. Clean up k3d internals
ssh astronomy-shop-us "sudo /usr/local/bin/k3d-cleanup.sh"

# 4. Remove old images from k3d nodes
ssh astronomy-shop-us 'for container in $(docker ps --filter "name=k3d" --format "{{.Names}}"); do docker exec $container crictl rmi --prune; done'
```

### When Memory is Exhausted

```bash
# Check which pods are using the most memory
kubectl top pods -A --sort-by=memory

# Restart high-memory pods
kubectl rollout restart deployment/<deployment-name>

# Scale down non-critical services temporarily
kubectl scale deployment <non-critical-service> --replicas=0
```

### When CPU is Pegged

```bash
# Identify CPU hogs
kubectl top pods -A --sort-by=cpu

# Check for pods in CrashLoopBackOff
kubectl get pods -A | grep CrashLoop

# Review pod logs for errors
kubectl logs <pod-name> --tail=100
```

---

## Part 6: Long-Term Strategy

### 6.1 Regular Maintenance Schedule

| Frequency | Task | Command |
|-----------|------|---------|
| Daily | Quick cleanup | Automated via cron |
| Weekly | Full cleanup | Automated via cron |
| Monthly | Manual review | Check logs, verify autocleanup |
| Quarterly | Cluster rebuild | Fresh start, apply learnings |

### 6.2 Capacity Planning

Monitor trends over time:

```bash
# Create a simple trend log
echo "$(date),$(df / | tail -1 | awk '{print $5}'),$(docker system df | grep 'Images' | awk '{print $4}')" >> /var/log/capacity-trends.csv
```

Add to cron:
```bash
0 0 * * * root echo "$(date),$(df / | tail -1 | awk '{print $5}'),$(docker system df | grep 'Images' | awk '{print $4}')" >> /var/log/capacity-trends.csv
```

Review monthly to identify:
- Growth rate of disk usage
- When you'll need more storage
- Which services consume the most resources

### 6.3 Consider Upgrade Paths

If you consistently hit resource limits:

**Option A: Increase host resources**
- Resize EC2 instance (if on AWS)
- Add more disk space
- Add more RAM/CPU

**Option B: Move to multi-node k3d**
```bash
k3d cluster create astronomy-shop-us-cluster \
  --servers 1 \
  --agents 3  # More agent nodes = distribute load
```

**Option C: Migrate to real Kubernetes**
- EKS (AWS)
- GKE (Google Cloud)
- AKS (Azure)
- Self-managed k8s cluster

---

## Summary: Recommended Implementation

### Phase 1: Immediate (Do Today)
1. ✅ Configure Docker log rotation (Solution 1)
2. ✅ Clean up existing logs (Solution 2)
3. ✅ Prune unused images (Solution 3)
4. ✅ Deploy k3d-cleanup script
5. ✅ Set up cron jobs

### Phase 2: Short-term (This Week)
1. Add resource requests/limits to all pods
2. Deploy resource quotas and limit ranges
3. Set up monitoring script
4. Install metrics-server
5. Create PodDisruptionBudgets for critical services

### Phase 3: Long-term (Next Maintenance Window)
1. Rebuild cluster with optimized configuration
2. Implement HPA for scalable services
3. Set up proper alerting
4. Document runbooks for common issues
5. Schedule quarterly cluster rebuilds

---

## Quick Reference Commands

```bash
# Check disk usage
df -h / && docker system df

# Quick cleanup
docker system prune -f

# K3d-specific cleanup
for c in $(docker ps --filter "name=k3d" -q); do docker exec $c crictl rmi --prune; done

# Check resource usage
kubectl top nodes && kubectl top pods -A --sort-by=memory

# View cleanup logs
tail -f /var/log/k3d-cleanup.log

# Manual trigger full cleanup
sudo /usr/local/bin/k3d-cleanup.sh
```

---

**Document Version**: 1.0
**Last Updated**: February 12, 2026
**Best for**: k3d clusters running production-like workloads
