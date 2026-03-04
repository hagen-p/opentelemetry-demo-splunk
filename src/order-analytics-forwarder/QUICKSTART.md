# Order Analytics Forwarder - Quick Start Guide

Get the order analytics forwarder running in 5 minutes!

## Overview

This service consumes orders from Kafka and forwards them to AWS Lambda for analytics processing.

**Key Feature: Distributed Trace Context Propagation** - The service extracts trace context from Kafka message headers, creating proper parent-child relationships in distributed traces (not span links!).

```
┌─────────────┐      ┌──────────┐      ┌────────────────────────────┐      ┌──────────────┐
│  Checkout   │─────▶│  Kafka   │─────▶│ Order Analytics Forwarder  │─────▶│ AWS Lambda   │
│  Service    │      │  orders  │      │   (This Service)           │      │  Analytics   │
└─────────────┘      └──────────┘      └────────────────────────────┘      └──────────────┘
                          ↓
                   Trace Context
                   in Headers
```

## Quick Start - Local Development (No Lambda)

Run the service locally without AWS Lambda (it will log orders instead):

```bash
# 1. Install dependencies
cd src/order-analytics-forwarder
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Set environment variables
export KAFKA_ADDR=localhost:9092
export OTEL_SERVICE_NAME=order-analytics-forwarder
# Leave LAMBDA_FUNCTION_NAME empty to use log mode

# 3. Run the service with Splunk OpenTelemetry instrumentation
opentelemetry-instrument python order_forwarder.py
```

The service will now consume orders from Kafka and log them to stdout.

## Quick Start - Kubernetes (With Lambda)

### Prerequisites
- Kubernetes cluster with OpenTelemetry Demo running
- AWS Lambda function deployed (see `lambda-example/README.md`)
- AWS credentials

### Step 1: Create AWS credentials secret

```bash
kubectl create secret generic aws-credentials \
  --from-literal=access-key-id=YOUR_ACCESS_KEY_ID \
  --from-literal=secret-access-key=YOUR_SECRET_ACCESS_KEY
```

### Step 2: Update deployment with your Lambda function

Edit `order-analytics-forwarder-k8s.yaml`:

```yaml
- name: LAMBDA_FUNCTION_NAME
  value: 'order-analytics-processor'  # Your Lambda function name
- name: AWS_REGION
  value: 'us-east-1'  # Your AWS region
```

Uncomment AWS credentials section:

```yaml
- name: AWS_ACCESS_KEY_ID
  valueFrom:
    secretKeyRef:
      name: aws-credentials
      key: access-key-id
- name: AWS_SECRET_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: aws-credentials
      key: secret-access-key
```

### Step 3: Build and deploy

```bash
# Build the Docker image
./build.sh

# Push to your registry (update IMAGE_NAME in build.sh first)
docker push ghcr.io/YOUR_ORG/opentelemetry-demo/otel-order-analytics-forwarder:1.6.0

# Deploy to Kubernetes
kubectl apply -f order-analytics-forwarder-k8s.yaml
```

### Step 4: Verify it's working

```bash
# Check pod status
kubectl get pods -l app.kubernetes.io/name=order-analytics-forwarder

# View logs
kubectl logs -l app.kubernetes.io/name=order-analytics-forwarder --tail=50 -f

# Look for messages like:
# "Order abc123 forwarded to Lambda successfully"
```

## Quick Start - Docker Compose (Local Testing)

If you're running the demo with Docker Compose:

1. Add to `docker-compose.yaml`:

```yaml
order-analytics-forwarder:
  image: order-analytics-forwarder:latest
  build:
    context: ./
    dockerfile: ./src/order-analytics-forwarder/Dockerfile
  environment:
    - KAFKA_ADDR=kafka:9092
    - OTEL_SERVICE_NAME=order-analytics-forwarder
    - OTEL_EXPORTER_OTLP_ENDPOINT=http://otelcol:4318
    - FLAGD_HOST=flagd
    - FLAGD_PORT=8013
    # Uncomment to enable Lambda forwarding
    # - LAMBDA_FUNCTION_NAME=order-analytics-processor
    # - AWS_REGION=us-east-1
    # - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
    # - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
  depends_on:
    - kafka
    - flagd
    - otelcol
```

2. Run:

```bash
docker-compose up order-analytics-forwarder
```

## Testing the Service

### Generate test orders

If you have the demo running, place an order through the frontend:

```bash
# Port-forward the frontend
kubectl port-forward svc/frontend-proxy 8080:8080

# Open in browser
open http://localhost:8080
```

Or use the load generator:

```bash
# Port-forward loadgen
kubectl port-forward svc/frontend-proxy 8080:8080

# Access loadgen UI
open http://localhost:8080/loadgen
```

### Monitor processing

Watch the logs to see orders being processed:

```bash
kubectl logs -l app.kubernetes.io/name=order-analytics-forwarder -f
```

You should see:
```json
{
  "timestamp": "2026-03-03T14:15:30.123Z",
  "levelname": "INFO",
  "message": "Processing order: abc-123-def-456",
  "trace_id": "79121a21a3d300b7835e74f60451c732"
}
```

### Check Lambda execution (if configured)

View Lambda logs:

```bash
aws logs tail /aws/lambda/order-analytics-processor --follow
```

Or in AWS Console:
- Go to Lambda → order-analytics-processor → Monitor → View logs in CloudWatch

## Observability

### View Traces in Splunk

1. Go to your Splunk Observability Cloud
2. Navigate to APM → Traces
3. Search for service: `order-analytics-forwarder`
4. Click on a trace to see the full flow:
   - Kafka message consumption
   - Order processing
   - Lambda invocation

### View Metrics

Custom metrics available:
- `app.orders.forwarded` - Total orders forwarded
- `app.orders.forwarding_errors` - Forwarding errors
- `app.kafka.messages_consumed` - Kafka messages consumed
- `app.lambda.invocation_duration` - Lambda invocation time

### View Logs

Structured JSON logs with trace correlation:

```bash
# Kubernetes
kubectl logs -l app.kubernetes.io/name=order-analytics-forwarder --tail=100

# In Splunk
index=otel service.name=order-analytics-forwarder
```

## Common Issues

### "Failed to connect to Kafka"
- Verify Kafka is running: `kubectl get pods -l app=kafka`
- Check KAFKA_ADDR environment variable
- Ensure init container waits for Kafka

### "Lambda invocation failed"
- Check AWS credentials are set correctly
- Verify Lambda function exists in the region
- Check IAM permissions for Lambda invoke
- View Lambda errors in CloudWatch logs

### "No messages being consumed"
- Verify orders are being created (check checkout service)
- Check Kafka topic exists: `kubectl exec -it kafka-0 -- kafka-topics.sh --list --bootstrap-server localhost:9092`
- Check consumer group: `kafka-consumer-groups.sh --describe --group order-analytics-forwarder`

## Next Steps

1. **Deploy Lambda function**: See `lambda-example/README.md`
2. **Configure data storage**: Choose DynamoDB, S3, or Kinesis
3. **Set up monitoring**: Create CloudWatch dashboards and alarms
4. **Customize analytics**: Extend the Lambda function for your needs
5. **Scale the service**: Increase replicas for higher throughput

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenTelemetry Demo                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────┐                                                    │
│  │ Frontend │──────────┐                                         │
│  └──────────┘          │                                         │
│                        ▼                                         │
│                  ┌──────────┐                                    │
│                  │ Checkout │                                    │
│                  │ Service  │                                    │
│                  └─────┬────┘                                    │
│                        │                                         │
│                        ▼                                         │
│              ┌─────────────────┐                                 │
│              │  Kafka (orders) │                                 │
│              └────┬──────┬─────┘                                 │
│                   │      │                                       │
│          ┌────────┘      └────────┐                              │
│          ▼                        ▼                              │
│  ┌───────────────┐    ┌──────────────────────┐                  │
│  │Fraud Detection│    │Order Analytics       │                  │
│  │   Service     │    │Forwarder (NEW!)      │                  │
│  └───────┬───────┘    └──────────┬───────────┘                  │
│          │                       │                               │
│          ▼                       ▼                               │
│   ┌──────────┐           ┌──────────────┐                       │
│   │SQL Server│           │External:     │                       │
│   │          │           │AWS Lambda    │                       │
│   └──────────┘           └──────┬───────┘                       │
│                                 │                                │
└─────────────────────────────────┼────────────────────────────────┘
                                  │
                          ┌───────▼────────┐
                          │  AWS Services  │
                          ├────────────────┤
                          │ • DynamoDB     │
                          │ • S3           │
                          │ • Kinesis      │
                          │ • CloudWatch   │
                          └────────────────┘
```

## Support

- **Issues**: [GitHub Issues](https://github.com/splunk/opentelemetry-demo/issues)
- **Documentation**: See `README.md` in this directory
- **Lambda Setup**: See `lambda-example/README.md`

## License

Copyright The OpenTelemetry Authors
SPDX-License-Identifier: Apache-2.0
