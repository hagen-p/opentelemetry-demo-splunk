# Remote Warehouse Service

## Overview

The **remote-warehouse** service is a Python-based Kafka consumer that demonstrates how to continue distributed traces across asynchronous message queues.

Unlike the `accounting` and `fraud-detection` services which create **span links**, the `remote-warehouse` service extracts trace context from Kafka message headers and creates spans **within the existing trace**, making it appear as a continuation of the order processing flow.

## Architecture

```
Checkout Service
    └─ [Produces to Kafka: "orders" topic]
            ├─ Accounting Service (span link)
            ├─ Fraud Detection Service (span link)
            └─ Remote Warehouse Service (continues trace) ← This service
```

## Key Features

### 1. Trace Continuation (Not Span Links)

The service extracts W3C Trace Context from Kafka message headers:
- `traceparent`: Contains trace ID, span ID, and trace flags
- `tracestate`: Contains vendor-specific trace information

This allows the warehouse processing span to appear as a **direct child** in the trace, rather than a separate linked trace.

### 2. CONSUMER Span Kind

Creates spans with `SpanKind.CONSUMER` to indicate message queue consumption:
- Properly categorizes the operation in trace visualizations
- Helps identify asynchronous processing boundaries
- Distinguishes from INTERNAL spans (accounting) and CLIENT spans (API calls)

### 3. Span Attributes

The service sets meaningful attributes for observability:

**Messaging attributes:**
- `messaging.system`: "kafka"
- `messaging.destination`: "orders"
- `messaging.operation`: "process"
- `messaging.consumer.group`: "remote-warehouse"

**Business attributes:**
- `order.id`: Order identifier
- `order.items.count`: Number of items in the order
- `warehouse.total_items`: Total quantity across all items
- `warehouse.shipping_tracking_id`: Shipping tracking reference

### 4. Span Events

The service adds events for each item processed:
```python
span.add_event(
    "warehouse.item_processed",
    attributes={
        "item.index": idx,
        "item.product_id": item.item.product_id,
        "item.quantity": item.item.quantity,
    }
)
```

## Technical Details

### Dependencies

- **confluent-kafka**: Kafka consumer client
- **protobuf**: Message deserialization (OrderResult)
- **opentelemetry-api**: Core OpenTelemetry API
- **opentelemetry-sdk**: OpenTelemetry SDK implementation
- **opentelemetry-exporter-otlp-proto-http**: OTLP HTTP exporter

### Message Format

Consumes protobuf messages from the `orders` topic with the schema defined in `demo.proto`:

```protobuf
message OrderResult {
  string order_id = 1;
  string shipping_tracking_id = 2;
  repeated OrderItem items = 3;
  Money shipping_cost = 4;
  Address shipping_address = 5;
}
```

### Trace Context Extraction

Uses W3C Trace Context propagation:

```python
propagator = TraceContextTextMapPropagator()
trace_context = propagator.extract(carrier=headers_dict)
```

The extracted context is set as the parent for the new span:

```python
ctx = context.attach(message_context)
with tracer.start_as_current_span("process-warehouse-order", kind=SpanKind.CONSUMER):
    # Processing logic
```

## Comparison with Other Services

| Service | Trace Relationship | Span Kind | Use Case |
|---------|-------------------|-----------|----------|
| **Accounting** | Span Link | INTERNAL | Async processing, separate trace context |
| **Fraud Detection** | Span Link | INTERNAL | Async processing, separate trace context |
| **Remote Warehouse** | Trace Continuation | CONSUMER | Continues the trace, appears as direct child |

### When to Use Each Pattern

**Span Links** (Accounting, Fraud Detection):
- Processing can happen much later
- Business logic is independent of the original request
- Want to correlate but not block on the original trace

**Trace Continuation** (Remote Warehouse):
- Processing is logically part of the original operation
- Want to see the full flow in a single trace
- End-to-end latency matters for the business flow

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_ADDR` | `kafka:9092` | Kafka bootstrap servers |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTLP endpoint for traces |
| `OTEL_SERVICE_NAME` | `remote-warehouse` | Service name in traces |
| `SERVICE_NAMESPACE` | `opentelemetry-demo` | Service namespace |
| `SERVICE_VERSION` | `2.1.3` | Service version |

## Resource Attributes

The service sets a special resource attribute to indicate its Kafka role:

```yaml
service.kafka=consumer  # Indicates this service consumes and continues traces
```

Compare with:
- `service.kafka=spanlink` (Accounting, Fraud Detection)
- `service.kafka=no` (Services not using Kafka)

## Building and Running

### Local Development

```bash
cd src/remote-warehouse

# Install dependencies
pip install -r requirements.txt

# Generate protobuf files
./generate_proto.sh

# Run the consumer
python3 consumer.py
```

### Docker Build

```bash
docker build -t otel-remote-warehouse:latest .
docker run -e KAFKA_ADDR=localhost:9092 otel-remote-warehouse:latest
```

### Kubernetes Deployment

The service is deployed as part of the Astronomy Shop:

```bash
kubectl apply -f remote-warehouse-k8s.yaml
```

Monitor the deployment:

```bash
# Check pod status
kubectl get pods -l app.kubernetes.io/component=remote-warehouse -n astronomy-shop

# View logs
kubectl logs -l app.kubernetes.io/component=remote-warehouse -n astronomy-shop -f
```

## Observability

### Traces in Splunk Observability Cloud

When viewing a checkout trace, you'll see:
1. Frontend → Checkout Service
2. Checkout → Kafka Producer
3. **Remote Warehouse CONSUMER span** (this service) ← Appears as child span
4. Remote Warehouse processing events

### Attributes Promoted

Because the service uses `SpanKind.CONSUMER`, Splunk O11y promotes the following attributes:
- `messaging.system`
- `messaging.destination`
- `order.id`
- `warehouse.total_items`

### Example Queries

**Find all warehouse processing spans:**
```
span.kind=consumer AND service.name=remote-warehouse
```

**Find orders with many items:**
```
warehouse.total_items > 5
```

**Trace warehouse latency:**
```
service.name=remote-warehouse AND operation=process-warehouse-order
```

## Troubleshooting

### No spans appearing

Check that:
1. Kafka is reachable: `kubectl logs -l app.kubernetes.io/component=remote-warehouse -n astronomy-shop`
2. OTLP endpoint is correct
3. Trace context is present in Kafka headers

### Spans not connected to trace

Verify that:
1. Checkout service is propagating trace context to Kafka headers
2. The propagator is extracting `traceparent` correctly
3. Message headers contain trace context

### High memory usage

The service processes messages synchronously. For high-throughput scenarios:
- Increase memory limits in `remote-warehouse-k8s.yaml`
- Consider batch processing
- Adjust Kafka consumer group settings

## References

- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry Python SDK](https://opentelemetry-python.readthedocs.io/)
- [Kafka Message Headers](https://kafka.apache.org/documentation/#recordheader)
- [Span Links vs Parent-Child Relationships](https://opentelemetry.io/docs/concepts/signals/traces/#span-links)
