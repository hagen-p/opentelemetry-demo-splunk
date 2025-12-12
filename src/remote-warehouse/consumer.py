#!/usr/bin/env python3
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os
import logging
import sys
import time
from typing import Dict, Any

from confluent_kafka import Consumer, KafkaError, KafkaException
from google.protobuf.json_format import MessageToDict

# OpenTelemetry imports
from opentelemetry import trace, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.trace import SpanKind, Status, StatusCode

# Import the protobuf message definition
import demo_pb2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_ADDR = os.getenv('KAFKA_ADDR', 'kafka:9092')
KAFKA_TOPIC = 'orders'
CONSUMER_GROUP = 'remote-warehouse'
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318')
SERVICE_NAME = os.getenv('OTEL_SERVICE_NAME', 'remote-warehouse')
SERVICE_NAMESPACE = os.getenv('SERVICE_NAMESPACE', 'opentelemetry-demo')
SERVICE_VERSION = os.getenv('SERVICE_VERSION', '2.1.3')

# Initialize OpenTelemetry
resource = Resource.create({
    "service.name": SERVICE_NAME,
    "service.namespace": SERVICE_NAMESPACE,
    "service.version": SERVICE_VERSION,
    "service.kafka": "consumer"  # Mark as consumer (not spanlink)
})

trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

# Configure OTLP exporter
otlp_exporter = OTLPSpanExporter(endpoint=f"{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces")
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# Instrument logging
LoggingInstrumentor().instrument(set_logging_format=True)

# Trace context propagator
propagator = TraceContextTextMapPropagator()


def extract_trace_context_from_headers(headers: list) -> context.Context:
    """
    Extract trace context from Kafka message headers.

    Headers come as list of tuples: [('traceparent', b'00-...'), ('tracestate', b'...')]
    """
    if not headers:
        return context.get_current()

    # Convert headers to dict format expected by propagator
    carrier = {}
    for key, value in headers:
        if isinstance(value, bytes):
            carrier[key] = value.decode('utf-8')
        else:
            carrier[key] = value

    # Extract context using W3C Trace Context propagator
    return propagator.extract(carrier=carrier)


def process_order(order: demo_pb2.OrderResult, message_context: context.Context) -> None:
    """
    Process an order message and create a span in the existing trace.
    """
    # Set the extracted context as active
    ctx = context.attach(message_context)

    try:
        # Create a CONSUMER span that continues the trace
        with tracer.start_as_current_span(
            "process-warehouse-order",
            kind=SpanKind.CONSUMER,
            attributes={
                "messaging.system": "kafka",
                "messaging.destination": KAFKA_TOPIC,
                "messaging.operation": "process",
                "messaging.consumer.group": CONSUMER_GROUP,
                "order.id": order.order_id,
                "order.items.count": len(order.items),
            }
        ) as span:
            logger.info(f"Processing order {order.order_id} in warehouse")

            # Simulate warehouse processing
            total_items = sum(item.item.quantity for item in order.items)

            span.set_attribute("warehouse.total_items", total_items)
            span.set_attribute("warehouse.shipping_tracking_id", order.shipping_tracking_id)

            # Log each item
            for idx, item in enumerate(order.items):
                span.add_event(
                    f"warehouse.item_processed",
                    attributes={
                        "item.index": idx,
                        "item.product_id": item.item.product_id,
                        "item.quantity": item.item.quantity,
                    }
                )

            # Simulate processing time
            time.sleep(0.1)

            logger.info(
                f"Warehouse processed order {order.order_id}: "
                f"{total_items} items, shipping={order.shipping_tracking_id}"
            )

            span.set_status(Status(StatusCode.OK))

    except Exception as e:
        logger.error(f"Error processing order: {e}", exc_info=True)
        if 'span' in locals():
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
        raise
    finally:
        context.detach(ctx)


def create_kafka_consumer() -> Consumer:
    """Create and configure Kafka consumer."""
    conf = {
        'bootstrap.servers': KAFKA_ADDR,
        'group.id': CONSUMER_GROUP,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': True,
    }

    consumer = Consumer(conf)
    consumer.subscribe([KAFKA_TOPIC])
    logger.info(f"Subscribed to Kafka topic '{KAFKA_TOPIC}' at {KAFKA_ADDR}")

    return consumer


def main():
    """Main consumer loop."""
    logger.info(f"Starting Remote Warehouse Service")
    logger.info(f"Kafka: {KAFKA_ADDR}")
    logger.info(f"Topic: {KAFKA_TOPIC}")
    logger.info(f"OTLP Endpoint: {OTEL_EXPORTER_OTLP_ENDPOINT}")

    consumer = create_kafka_consumer()

    try:
        while True:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.debug(f"Reached end of partition {msg.partition()}")
                else:
                    raise KafkaException(msg.error())
                continue

            try:
                # Extract trace context from message headers
                trace_context = extract_trace_context_from_headers(msg.headers())

                # Parse the protobuf message
                order = demo_pb2.OrderResult()
                order.ParseFromString(msg.value())

                # Process the order with the extracted trace context
                process_order(order, trace_context)

            except Exception as e:
                logger.error(f"Failed to process message: {e}", exc_info=True)

    except KeyboardInterrupt:
        logger.info("Shutting down consumer...")

    finally:
        consumer.close()
        # Flush telemetry
        trace.get_tracer_provider().force_flush()
        logger.info("Consumer closed")


if __name__ == '__main__':
    main()
