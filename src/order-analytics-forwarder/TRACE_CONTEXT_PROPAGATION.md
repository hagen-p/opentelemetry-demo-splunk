# Trace Context Propagation Implementation

This document explains how the order-analytics-forwarder service implements proper trace context propagation from Kafka messages.

## Problem Statement

By default, without trace context extraction, Kafka consumers create **new root traces** or use **span links** instead of creating proper parent-child relationships. This breaks the distributed trace flow:

```
❌ Without Context Extraction:
Frontend → Checkout → Kafka Publish (Trace 1 ends here)
                           ↓
            Order Forwarder (NEW Trace 2 starts)
```

We want proper parent-child relationships:

```
✅ With Context Extraction:
Frontend → Checkout → Kafka Publish
                           ↓ (trace context in headers)
            Order Forwarder (continues Trace 1 as child)
                           ↓
            AWS Lambda (still part of Trace 1)
```

## Implementation

### 1. Added Imports

```python
from opentelemetry import trace, context, propagate
```

- `context` - For managing OpenTelemetry context
- `propagate` - For extracting trace context from carriers (headers)

### 2. Context Extraction Method

Created `_extract_trace_context()` method that:

1. Reads Kafka message headers (list of tuples)
2. Converts headers to dict format
3. Uses `propagate.extract()` to extract W3C Trace Context
4. Returns the extracted context

```python
def _extract_trace_context(self, message) -> context.Context:
    """Extract OpenTelemetry trace context from Kafka message headers"""

    # Convert Kafka headers: [(key, value), ...] → {key: value}
    carrier = {}
    for key, value in message.headers:
        if isinstance(value, bytes):
            carrier[key] = value.decode('utf-8')
        else:
            carrier[key] = value

    # Extract using OpenTelemetry propagator (looks for traceparent, tracestate)
    extracted_context = propagate.extract(carrier)

    return extracted_context
```

### 3. Updated Message Processing

Modified `process_message()` to:

1. Extract trace context from headers
2. Attach that context before starting spans
3. Start span with `SpanKind.CONSUMER`
4. Detach context after processing

```python
def process_message(self, message):
    # Extract parent trace context from Kafka headers
    extracted_context = self._extract_trace_context(message)

    # Attach the extracted context
    ctx_token = context.attach(extracted_context)

    try:
        # Start span within the extracted context
        with self.tracer.start_as_current_span(
            "process_kafka_message",
            kind=trace.SpanKind.CONSUMER,  # Important: CONSUMER span kind
        ) as span:
            # This span is now a child of the Kafka producer's span
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination.name", message.topic)
            # ... process message
    finally:
        # Clean up: detach the context
        context.detach(ctx_token)
```

### 4. Added Kafka Semantic Conventions

Following OpenTelemetry semantic conventions for messaging:

```python
span.set_attribute("messaging.system", "kafka")
span.set_attribute("messaging.destination.name", message.topic)
span.set_attribute("messaging.kafka.partition", message.partition)
span.set_attribute("messaging.kafka.offset", message.offset)
span.set_attribute("messaging.kafka.consumer.group", CONSUMER_GROUP_ID)
span.set_attribute("messaging.operation", "receive")
```

## How Trace Context Flows

### Producer Side (Checkout Service)

When checkout service publishes to Kafka, OpenTelemetry instrumentation automatically:

1. Gets current span context
2. Injects context into message headers using W3C Trace Context format
3. Publishes message with headers

Example headers added:
```
traceparent: 00-79121a21a3d300b7835e74f60451c732-9dc40e89de7405f-01
tracestate: vendor1=value1
```

### Consumer Side (This Service)

When we consume the message:

1. Read headers from Kafka message
2. Extract trace context using `propagate.extract()`
3. Attach that context before starting spans
4. All spans created within that context become children of the producer's span

### W3C Trace Context Format

The `traceparent` header format:
```
version-trace_id-parent_span_id-trace_flags
00-79121a21a3d300b7835e74f60451c732-9dc40e89de7405f-01
```

Where:
- `version` = 00 (W3C standard version)
- `trace_id` = 32 hex chars (128-bit)
- `parent_span_id` = 16 hex chars (64-bit)
- `trace_flags` = 01 (sampled) or 00 (not sampled)

## Verification

### Check Logs

Enable debug logging to see trace context extraction:

```bash
export OTEL_LOG_LEVEL=debug
```

Look for log messages:
```
"Extracted trace context - trace_id: 79121a21a3d300b7835e74f60451c732, span_id: 9dc40e89de7405f"
```

### Verify in APM

In Splunk APM or Jaeger:

1. Find a checkout trace
2. Navigate to the Kafka publish span
3. Look for child spans from `order-analytics-forwarder`
4. Verify: **Parent-child relationship** (not span links)

**Expected trace structure:**
```
Trace ID: 79121a21a3d300b7835e74f60451c732
├─ frontend: GET /api/checkout
│  └─ checkout: PlaceOrder (gRPC)
│     └─ kafka-producer: orders publish  ← Producer span
│        └─ order-analytics-forwarder: process_kafka_message ← Our span (CHILD!)
│           └─ order-analytics-forwarder: forward_to_lambda
│              └─ aws-lambda: order-analytics-processor
```

### Test Without Headers

To verify the service handles missing headers gracefully:

```python
# Message without headers returns current context
message_without_headers = Mock(headers=None)
ctx = forwarder._extract_trace_context(message_without_headers)
# Should not crash, returns current context
```

## Best Practices

### ✅ DO:
- Extract context before starting spans
- Use `context.attach()` / `context.detach()`
- Set span kind to `CONSUMER` for message consumers
- Use semantic conventions for messaging attributes
- Handle missing headers gracefully

### ❌ DON'T:
- Start spans before extracting context
- Forget to detach context (causes context leaks)
- Use `INTERNAL` span kind for Kafka consumers
- Assume headers are always present
- Create new trace IDs for messages

## Compatibility

This implementation uses:
- **W3C Trace Context** standard (widely supported)
- **OpenTelemetry Python SDK** 1.20+
- **Kafka message headers** (Kafka 0.11+)

Compatible with:
- ✅ OpenTelemetry SDKs (all languages)
- ✅ Jaeger
- ✅ Zipkin (with appropriate propagators)
- ✅ Splunk APM
- ✅ AWS X-Ray (with X-Ray propagator)
- ✅ Google Cloud Trace

## Troubleshooting

### Issue: No parent relationship in traces

**Possible causes:**
1. Checkout service not injecting trace context
2. Kafka broker dropping headers (old Kafka version)
3. Consumer not extracting headers properly

**Solution:**
```bash
# Check Kafka message headers
kafka-console-consumer --bootstrap-server kafka:9092 \
  --topic orders \
  --property print.headers=true \
  --max-messages 1

# Should see: traceparent:...
```

### Issue: Trace context extraction logs "No valid trace context"

**Possible causes:**
1. Headers are present but malformed
2. Wrong propagator configured

**Solution:**
```python
# Debug: Print raw headers
logger.info(f"Raw Kafka headers: {message.headers}")

# Verify propagator is configured
from opentelemetry import propagate
logger.info(f"Propagator: {propagate.get_global_textmap()}")
```

### Issue: Context leaks / memory issues

**Cause:** Not calling `context.detach()`

**Solution:** Always use try/finally:
```python
ctx_token = context.attach(extracted_context)
try:
    # ... do work
finally:
    context.detach(ctx_token)  # Critical!
```

## References

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry Semantic Conventions: Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/)
- [Kafka Message Format](https://kafka.apache.org/documentation/#recordbatch)

## License

Copyright The OpenTelemetry Authors
SPDX-License-Identifier: Apache-2.0
