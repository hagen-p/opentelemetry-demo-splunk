# Order Analytics Forwarder Service

A Python microservice that consumes orders from the Kafka `orders` topic and forwards them to AWS Lambda for analytics processing.

## Overview

This service:
- Consumes order events from Kafka topic `orders`
- Deserializes protobuf OrderResult messages
- Forwards orders to a configurable AWS Lambda function for analytics
- Provides comprehensive OpenTelemetry instrumentation (traces, metrics, logs)
- Supports feature flags for runtime configuration

## Architecture

```
Kafka (orders topic)
      ↓
Order Analytics Forwarder
      ↓
AWS Lambda (analytics-processor)
```

## Features

- **Kafka Consumer**: Connects to Kafka and consumes from the `orders` topic
- **AWS Lambda Integration**: Asynchronous invocation of Lambda functions
- **OpenTelemetry Instrumentation**:
  - Distributed tracing with custom spans
  - Custom metrics for orders forwarded, errors, and Lambda duration
  - Structured JSON logging with trace correlation
- **Feature Flags**: Runtime configuration via flagd/OpenFeature
- **Graceful Error Handling**: Retries and error logging
- **Fallback Mode**: Logs orders when Lambda is not configured

## Configuration

### Environment Variables

#### Required
- `OTEL_SERVICE_NAME`: Service name for OpenTelemetry (default: `order-analytics-forwarder`)
- `KAFKA_ADDR`: Kafka bootstrap servers (e.g., `kafka:9092`)

#### Optional - AWS Lambda
- `LAMBDA_FUNCTION_NAME`: AWS Lambda function name (if empty, orders are logged instead)
- `AWS_REGION`: AWS region (default: `us-east-1`)
- `AWS_ACCESS_KEY_ID`: AWS access key (or use IAM roles)
- `AWS_SECRET_ACCESS_KEY`: AWS secret key (or use IAM roles)

#### Optional - OpenTelemetry
- `OTEL_EXPORTER_OTLP_ENDPOINT`: OTLP endpoint (default: `http://localhost:4318`)
- `OTEL_PYTHON_LOG_CORRELATION`: Enable log correlation (default: `true`)

#### Optional - Feature Flags
- `FLAGD_HOST`: Flagd service host (default: `flagd`)
- `FLAGD_PORT`: Flagd service port (default: `8013`)

## Metrics

The service exposes the following custom metrics:

- `app.orders.forwarded` - Counter of orders forwarded to Lambda
- `app.orders.forwarding_errors` - Counter of forwarding errors
- `app.kafka.messages_consumed` - Counter of Kafka messages consumed
- `app.lambda.invocation_duration` - Histogram of Lambda invocation duration (ms)

## Feature Flags

- `disableOrderForwarding` (boolean): Temporarily disable order forwarding

## Local Development

### Prerequisites
- Python 3.12+
- Kafka running locally or accessible
- AWS credentials configured (if using Lambda)

### Install Dependencies
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run Locally
```bash
export KAFKA_ADDR=localhost:9092
export LAMBDA_FUNCTION_NAME=order-analytics-processor
export AWS_REGION=us-east-1
export OTEL_SERVICE_NAME=order-analytics-forwarder

# Run with auto-instrumentation
opentelemetry-instrument python order_forwarder.py
```

### Run Without Lambda (Log Mode)
```bash
export KAFKA_ADDR=localhost:9092
# Leave LAMBDA_FUNCTION_NAME empty
export OTEL_SERVICE_NAME=order-analytics-forwarder

opentelemetry-instrument python order_forwarder.py
```

## Docker Build

```bash
# From repository root
docker build -f src/order-analytics-forwarder/Dockerfile \
  -t order-analytics-forwarder:latest .
```

## Kubernetes Deployment

### Prerequisites
1. Kafka must be running in the cluster
2. Create AWS credentials secret (if using Lambda):
```bash
kubectl create secret generic aws-credentials \
  --from-literal=access-key-id=YOUR_ACCESS_KEY \
  --from-literal=secret-access-key=YOUR_SECRET_KEY
```

3. Update the deployment manifest to set your Lambda function name:
```yaml
- name: LAMBDA_FUNCTION_NAME
  value: 'your-lambda-function-name'
```

### Deploy
```bash
kubectl apply -f src/order-analytics-forwarder/order-analytics-forwarder-k8s.yaml
```

### Verify
```bash
# Check pod status
kubectl get pods -l app.kubernetes.io/name=order-analytics-forwarder

# View logs
kubectl logs -l app.kubernetes.io/name=order-analytics-forwarder --tail=100 -f
```

## AWS Lambda Function

The Lambda function should accept the following JSON payload structure:

```json
{
  "order_id": "550e8400-e29b-41d4-a716-446655440000",
  "shipping_tracking_id": "TRACK123456",
  "shipping_cost": {
    "currency_code": "USD",
    "units": 10,
    "nanos": 990000000
  },
  "shipping_address": {
    "street_address": "123 Main St",
    "city": "San Francisco",
    "state": "CA",
    "country": "US",
    "zip_code": "94102"
  },
  "items": [
    {
      "product_id": "PROD123",
      "quantity": 2,
      "cost": {
        "currency_code": "USD",
        "units": 29,
        "nanos": 990000000
      }
    }
  ]
}
```

See the `lambda-example/` directory for a sample Lambda function implementation (to be created).

## Observability

### Traces

**Distributed Trace Context Propagation:**

The service extracts OpenTelemetry trace context from Kafka message headers, creating proper parent-child relationships in the distributed trace:

```
Checkout Service (publish to Kafka)
    ↓ (trace context in Kafka headers)
Order Analytics Forwarder (consume from Kafka) ← YOU ARE HERE
    ↓
AWS Lambda (analytics processing)
```

This means traces will show:
1. **Parent span**: Checkout service publishing to Kafka
2. **Child span**: Order analytics forwarder consuming message (span kind: CONSUMER)
3. **Child spans**: Lambda invocation and processing

Every order processed creates a trace with spans:
- `process_kafka_message` (CONSUMER) - Overall message processing with parent trace from Kafka
- `forward_to_lambda` (CLIENT) - Lambda invocation (if configured)
- `log_order` (INTERNAL) - Order logging (fallback mode)

**Span attributes include:**

Kafka semantic conventions:
- `messaging.system` = "kafka"
- `messaging.destination.name` = "orders"
- `messaging.kafka.partition`
- `messaging.kafka.offset`
- `messaging.kafka.consumer.group` = "order-analytics-forwarder"
- `messaging.operation` = "receive"

Application-specific:
- `app.order.id`
- `app.order.items_count`
- `app.lambda.function`
- `app.lambda.status_code`
- `app.payload.size_bytes`

### Logs
Structured JSON logs include trace_id and span_id for correlation:
```json
{
  "timestamp": "2026-03-03T14:15:30.123Z",
  "levelname": "INFO",
  "name": "order-analytics-forwarder",
  "trace_id": "79121a21a3d300b7835e74f60451c732",
  "span_id": "9dc40e89de7405f",
  "message": "Order abc123 forwarded to Lambda successfully"
}
```

### Metrics
View metrics in your observability platform (Splunk, Grafana, etc.):
- Order throughput: `app.orders.forwarded`
- Error rate: `app.orders.forwarding_errors`
- Lambda performance: `app.lambda.invocation_duration`

## Troubleshooting

### Service doesn't consume messages
1. Check Kafka connectivity: `kubectl exec -it <pod> -- nc -zv kafka 9092`
2. Verify topic exists: Check Kafka broker for `orders` topic
3. Check consumer group: The service uses consumer group `order-analytics-forwarder`

### Lambda invocations fail
1. Verify AWS credentials are configured
2. Check IAM permissions for Lambda invoke
3. Verify Lambda function exists in the specified region
4. Check CloudWatch logs for Lambda errors

### No traces/metrics
1. Verify OTLP collector is running
2. Check `OTEL_EXPORTER_OTLP_ENDPOINT` is correct
3. View service logs for instrumentation errors

## Trace Context Propagation - Technical Details

### How It Works

1. **Producer Side (Checkout Service)**:
   - When checkout service publishes to Kafka, OpenTelemetry automatically injects trace context into message headers
   - Headers include: `traceparent`, `tracestate` (W3C Trace Context format)

2. **Consumer Side (This Service)**:
   ```python
   # Extract context from Kafka headers
   extracted_context = self._extract_trace_context(message)

   # Attach extracted context
   ctx_token = context.attach(extracted_context)

   # Start span with parent context
   with self.tracer.start_as_current_span("process_kafka_message", kind=CONSUMER):
       # This span is now a child of the producer's span
       ...

   # Clean up
   context.detach(ctx_token)
   ```

3. **Result**: Complete end-to-end trace:
   ```
   Frontend → Checkout → Kafka Publish → Kafka Consume → Lambda → Analytics Storage
   └─────────────────── Single Trace ID ──────────────────────────────────────┘
   ```

### Verification

To verify trace context is working:

```bash
# 1. Enable debug logging
export OTEL_LOG_LEVEL=debug

# 2. Check logs for trace context extraction
kubectl logs -l app.kubernetes.io/name=order-analytics-forwarder | grep "Extracted trace context"

# Expected output:
# "Extracted trace context - trace_id: 79121a21a3d300b7835e74f60451c732, span_id: ..."
```

In Splunk APM:
1. Find a trace starting from the frontend
2. Navigate through: Frontend → Checkout → Kafka publish
3. **You should see**: Order-analytics-forwarder spans as children of Kafka publish
4. **Not span links**: Direct parent-child relationship

### Kafka Headers Format

The service expects these headers in Kafka messages:

```python
{
  'traceparent': '00-{trace_id}-{span_id}-{trace_flags}',  # W3C format
  'tracestate': 'vendor1=value1,vendor2=value2'            # Optional
}
```

These are automatically added by OpenTelemetry Kafka instrumentation on the producer side.

## Integration with OpenTelemetry Demo

This service integrates with the existing OpenTelemetry demo architecture:

1. **Checkout Service** → Publishes orders to Kafka `orders` topic (with trace context headers)
2. **Order Analytics Forwarder** → Consumes orders, extracts parent trace context, forwards to Lambda
3. **Fraud Detection Service** → Also consumes from `orders` topic (parallel consumer with separate consumer group)

Both services can run simultaneously with different consumer groups and will both inherit the parent trace context from Kafka.

## License

Copyright The OpenTelemetry Authors
SPDX-License-Identifier: Apache-2.0
