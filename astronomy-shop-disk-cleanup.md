# Astronomy Shop US - Disk Usage Cleanup Guide

**Date**: February 12, 2026
**Server**: astronomy-shop-us
**Current Disk Usage**: 32GB/38GB (83% full)
**Target**: Reduce to ~50-60% usage

## Problem Summary

The astronomy-shop-us server is running out of disk space due to:

1. **Unrotated Docker container logs**: 2GB from two K3s agent containers (1GB each)
2. **Accumulated container images/layers**: ~11GB in containerd storage
3. **Legitimate database storage**: 2.2GB SQL Server (fraud-detection service)

### Key Finding: No Log Rotation Configured

Docker containers are using `json-file` logging driver with **empty configuration**, meaning:
- No maximum log file size
- No log rotation
- Logs grow indefinitely until disk fills up

## Investigation Details

### Disk Usage Breakdown

```
Filesystem: /dev/root
Total: 38GB
Used: 32GB (83%)
Available: 6.6GB

/var/lib/docker/: 23GB total
├── containers/: ~2GB (logs)
│   ├── k3d-astronomy-shop-us-cluster-agent-0: 1GB log
│   └── k3d-astronomy-shop-us-cluster-agent-1: 1GB log
├── volumes/: ~22GB
│   └── K3s server volume (5231da07...): 15.44GB
│       ├── containerd data: 11GB (images/snapshots)
│       └── storage/PVCs: 2.2GB (SQL Server fraud-detection)
```

### Container Log Analysis

```bash
# Current logging config (NO rotation!)
"LogConfig": {
    "Type": "json-file",
    "Config": {}
}
```

## Solutions

### Solution 1: Configure Docker Log Rotation (CRITICAL)

**Impact**: Prevents future log bloat, saves 2GB+ immediately after container restart
**Risk**: Low - Standard Docker configuration
**Downtime**: Requires Docker restart (k3d cluster will restart)

#### Steps:

1. Create Docker daemon configuration:

```bash
ssh astronomy-shop-us "sudo tee /etc/docker/daemon.json <<'EOF'
{
  \"log-driver\": \"json-file\",
  \"log-opts\": {
    \"max-size\": \"50m\",
    \"max-file\": \"3\"
  }
}
EOF"
```

2. Restart Docker (this will restart the k3d cluster):

```bash
ssh astronomy-shop-us "sudo systemctl restart docker"
```

3. Verify cluster comes back up:

```bash
ssh astronomy-shop-us "kubectl get pods -A"
```

**What this does**:
- Limits each container log to 50MB maximum size
- Keeps 3 rotated log files (150MB total per container)
- Applies to all new containers and existing containers after restart

### Solution 2: Clean Up Existing Large Log Files

**Impact**: Immediate 2GB disk space recovery
**Risk**: Very Low - Only truncates logs, doesn't affect running containers
**Downtime**: None

#### Steps:

```bash
# Truncate the two 1GB log files
ssh astronomy-shop-us "sudo truncate -s 0 /var/lib/docker/containers/d44f33f44975ca7536ded4b54e746bfcc709bfcc7051cbb916f2861431f2ebd3/d44f33f44975ca7536ded4b54e746bfcc709bfcc7051cbb916f2861431f2ebd3-json.log"

ssh astronomy-shop-us "sudo truncate -s 0 /var/lib/docker/containers/b6ddeb6cf1bc40a8e953f210837516bf6f8739b491945894b2add5672d330b04/b6ddeb6cf1bc40a8e953f210837516bf6f8739b491945894b2add5672d330b04-json.log"
```

**What this does**:
- Sets log file size to 0 bytes
- Containers continue running normally
- Logs will start accumulating again (but with rotation if Solution 1 is applied)

### Solution 3: Clean Up Unused Container Images/Layers

**Impact**: 5-8GB disk space recovery
**Risk**: Medium - Removes unused images (running containers unaffected)
**Downtime**: None for running services

#### Steps:

1. Check what will be removed (dry run):

```bash
ssh astronomy-shop-us "sudo docker system df -v"
```

2. Remove unused images, containers, and volumes:

```bash
ssh astronomy-shop-us "sudo docker system prune -a --volumes -f"
```

**⚠️ WARNING**: This will remove:
- All images not used by running containers
- All stopped containers
- Unused volumes (not attached to running containers)
- Build cache

**What gets preserved**:
- All running containers and their images
- All volumes currently mounted by running containers
- K3s cluster will continue running normally

### Solution 4: Configure Kubelet Log Rotation (OPTIONAL)

**Impact**: Additional protection at Kubernetes level
**Risk**: Low
**Downtime**: Requires k3d cluster recreation

If you want double protection, configure kubelet to rotate logs at the Kubernetes level:

```bash
# When recreating the k3d cluster, add these flags:
k3d cluster create astronomy-shop-us-cluster \
  --k3s-arg="--kubelet-arg=container-log-max-size=10Mi@server:*" \
  --k3s-arg="--kubelet-arg=container-log-max-files=5@server:*" \
  --k3s-arg="--kubelet-arg=container-log-max-size=10Mi@agent:*" \
  --k3s-arg="--kubelet-arg=container-log-max-files=5@agent:*"
```

**Note**: This requires cluster recreation, so only implement during planned maintenance.

### Solution 5: Automated Cleanup (LONG-TERM)

**Impact**: Prevents future disk space issues
**Risk**: Very Low
**Downtime**: None

Set up weekly automated cleanup:

```bash
ssh astronomy-shop-us "sudo tee /etc/cron.d/docker-cleanup <<'EOF'
# Clean up Docker system weekly (Sundays at 2 AM)
0 2 * * 0 root /usr/bin/docker system prune -f --volumes >> /var/log/docker-cleanup.log 2>&1
EOF"
```

## Recommended Implementation Order

### Immediate Actions (Do Today)

1. **Solution 2**: Truncate existing logs (2GB freed, no downtime)
2. **Solution 1**: Configure log rotation (prevents future issues, ~5 min downtime)
3. **Solution 3**: Prune unused images (5-8GB freed, no downtime)

**Expected Result**: Disk usage drops from 83% to ~50-60%

### Long-term Actions (Schedule for Maintenance Window)

4. **Solution 5**: Set up automated cleanup cron job
5. **Solution 4**: Configure kubelet log rotation (optional, next cluster rebuild)

## Verification Steps

After implementing solutions 1-3, verify the cleanup:

```bash
# Check disk usage
ssh astronomy-shop-us "df -h /"

# Check Docker disk usage
ssh astronomy-shop-us "sudo docker system df"

# Verify log rotation config
ssh astronomy-shop-us "cat /etc/docker/daemon.json"

# Verify cluster health
ssh astronomy-shop-us "kubectl get pods -A"

# Check new container log sizes (should be limited now)
ssh astronomy-shop-us "sudo find /var/lib/docker/containers -name '*-json.log' -exec du -sh {} \; 2>/dev/null | sort -hr | head -5"
```

## Using with Claude Code

If you're using Claude Code to implement these solutions, simply:

1. Share this document with Claude Code
2. Ask: "Please implement Solutions 1, 2, and 3 from the astronomy-shop-disk-cleanup.md document"
3. Claude Code will execute the commands in the correct order and verify results

## Rollback Plan

If something goes wrong:

### If Docker fails to start after Solution 1:
```bash
# Remove the daemon.json and restart
ssh astronomy-shop-us "sudo rm /etc/docker/daemon.json && sudo systemctl restart docker"
```

### If cluster doesn't come back up:
```bash
# Check Docker status
ssh astronomy-shop-us "sudo systemctl status docker"

# Check container status
ssh astronomy-shop-us "sudo docker ps -a"

# Restart k3d cluster manually if needed
ssh astronomy-shop-us "sudo docker restart \$(sudo docker ps -aq)"
```

## Questions?

- **Q**: Will this affect running services?
  - **A**: Solutions 1 & 2 may cause brief disruption when Docker restarts. Solution 3 only removes unused resources.

- **Q**: How often should we clean up?
  - **A**: Weekly automated cleanup (Solution 5) is recommended. Manual cleanup when disk > 70%.

- **Q**: What if we need the old logs?
  - **A**: Back up logs before truncating: `sudo cp <log-file> <backup-location>`

- **Q**: Why is containerd using 11GB?
  - **A**: Container image layers accumulate over time. This is normal but should be pruned regularly.

## Additional Monitoring

Consider setting up disk space alerts:

```bash
# Add to monitoring/alerting system
# Alert when disk usage > 75%
# Warning when disk usage > 70%
```

---

**Document Version**: 1.0
**Last Updated**: February 12, 2026
**Maintained By**: Platform Team
