#!/usr/bin/env python
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from opentelemetry import metrics

def init_metrics():
    """Initialize custom metrics for the order analytics forwarder"""

    meter = metrics.get_meter_provider().get_meter(__name__)

    # Counter for total orders forwarded to Lambda
    orders_forwarded_counter = meter.create_counter(
        name="app.orders.forwarded",
        description="Number of orders forwarded to AWS Lambda",
        unit="1"
    )

    # Counter for forwarding failures
    forwarding_errors_counter = meter.create_counter(
        name="app.orders.forwarding_errors",
        description="Number of errors when forwarding to Lambda",
        unit="1"
    )

    # Counter for Kafka messages consumed
    kafka_messages_counter = meter.create_counter(
        name="app.kafka.messages_consumed",
        description="Number of Kafka messages consumed from orders topic",
        unit="1"
    )

    # Histogram for Lambda invocation duration
    lambda_duration_histogram = meter.create_histogram(
        name="app.lambda.invocation_duration",
        description="Duration of Lambda invocations in milliseconds",
        unit="ms"
    )

    return {
        "orders_forwarded_counter": orders_forwarded_counter,
        "forwarding_errors_counter": forwarding_errors_counter,
        "kafka_messages_counter": kafka_messages_counter,
        "lambda_duration_histogram": lambda_duration_histogram
    }
