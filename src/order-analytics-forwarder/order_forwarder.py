#!/usr/bin/env python
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import json
import time
from typing import Optional

# Kafka
from kafka import KafkaConsumer
from kafka.errors import KafkaError

# AWS Lambda
import boto3
from botocore.exceptions import ClientError

# OpenTelemetry
from opentelemetry import trace, context, propagate
from opentelemetry import metrics as otel_metrics
from opentelemetry.trace import Status, StatusCode
from opentelemetry.semconv.trace import SpanAttributes

# Feature flags
from openfeature.api import get_client as get_feature_flag_client
from openfeature import api as feature_flag_api
from openfeature.provider.provider import FeatureProvider
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.hook.hook import Hook
from openfeature.contrib.hook.otel import TracingHook

# Local imports
from logger import setup_logger
from metrics import init_metrics
import demo_pb2

# Configuration
KAFKA_TOPIC = "orders"
CONSUMER_GROUP_ID = "order-analytics-forwarder"

# Initialize logger
logger = setup_logger("order-analytics-forwarder")

class OrderAnalyticsForwarder:
    """Consumes orders from Kafka and forwards them to AWS Lambda for analytics"""

    def __init__(self):
        self.service_name = os.getenv("OTEL_SERVICE_NAME", "order-analytics-forwarder")
        self.tracer = trace.get_tracer(self.service_name)
        self.metrics = init_metrics()

        # Kafka configuration
        self.kafka_address = self._get_required_env("KAFKA_ADDR")

        # AWS Lambda configuration
        self.lambda_function_name = os.getenv("LAMBDA_FUNCTION_NAME", "")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.use_lambda = bool(self.lambda_function_name)

        if not self.use_lambda:
            logger.warning("LAMBDA_FUNCTION_NAME not set - will log orders instead of forwarding")

        # Initialize AWS Lambda client
        self.lambda_client = None
        if self.use_lambda:
            try:
                self.lambda_client = boto3.client('lambda', region_name=self.aws_region)
                logger.info(f"AWS Lambda client initialized for region: {self.aws_region}")
            except Exception as e:
                logger.error(f"Failed to initialize Lambda client: {e}")
                self.use_lambda = False

        # Initialize Kafka consumer
        self.consumer = self._create_kafka_consumer()

        # Initialize feature flags
        self._init_feature_flags()

        # Statistics
        self.total_processed = 0
        self.total_forwarded = 0
        self.total_errors = 0

    def _get_required_env(self, key: str) -> str:
        """Get required environment variable or exit"""
        value = os.getenv(key)
        if not value:
            logger.error(f"Required environment variable {key} is not set")
            sys.exit(1)
        return value

    def _create_kafka_consumer(self) -> KafkaConsumer:
        """Create and configure Kafka consumer"""
        logger.info(f"Connecting to Kafka at {self.kafka_address}")

        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=self.kafka_address,
                group_id=CONSUMER_GROUP_ID,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                value_deserializer=lambda m: m,  # We'll deserialize protobuf manually
                consumer_timeout_ms=100,  # Poll timeout
            )
            logger.info(f"Kafka consumer created for topic: {KAFKA_TOPIC}")
            return consumer
        except KafkaError as e:
            logger.error(f"Failed to create Kafka consumer: {e}")
            sys.exit(1)

    def _init_feature_flags(self):
        """Initialize OpenFeature with flagd provider"""
        try:
            flagd_host = os.getenv("FLAGD_HOST", "flagd")
            flagd_port = int(os.getenv("FLAGD_PORT", "8013"))

            provider = FlagdProvider(
                host=flagd_host,
                port=flagd_port,
            )

            feature_flag_api.set_provider(provider)
            feature_flag_api.add_hooks([TracingHook()])

            logger.info(f"Feature flags initialized with flagd at {flagd_host}:{flagd_port}")
        except Exception as e:
            logger.warning(f"Failed to initialize feature flags: {e}")

    def _check_feature_flag(self, flag_name: str, default_value: bool = False) -> bool:
        """Check a feature flag value"""
        try:
            client = get_feature_flag_client()
            return client.get_boolean_value(flag_name, default_value)
        except Exception as e:
            logger.debug(f"Error checking feature flag {flag_name}: {e}")
            return default_value

    def _extract_trace_context(self, message) -> context.Context:
        """
        Extract OpenTelemetry trace context from Kafka message headers

        This enables distributed tracing by linking this service's spans
        to the parent trace from the producer (checkout service).

        Returns the extracted context or current context if no headers found.
        """
        if not message.headers:
            logger.debug("No Kafka headers found, using current context")
            return context.get_current()

        # Convert Kafka headers to dict format expected by propagator
        # Kafka headers are list of tuples: [(key, value), ...]
        # We need dict: {key: value}
        carrier = {}
        for key, value in message.headers:
            if value is not None:
                # Decode bytes to string if necessary
                if isinstance(value, bytes):
                    carrier[key] = value.decode('utf-8')
                else:
                    carrier[key] = value

        if not carrier:
            logger.debug("No trace context headers found in Kafka message")
            return context.get_current()

        # Extract context using OpenTelemetry propagator
        # This looks for standard W3C trace context headers (traceparent, tracestate)
        extracted_context = propagate.extract(carrier)

        # Log extracted trace context for debugging
        span_context = trace.get_current_span(extracted_context).get_span_context()
        if span_context.is_valid:
            trace_id = format(span_context.trace_id, '032x')
            span_id = format(span_context.span_id, '016x')
            logger.debug(f"Extracted trace context - trace_id: {trace_id}, span_id: {span_id}")
        else:
            logger.debug("No valid trace context extracted from headers")

        return extracted_context

    def _parse_order(self, message_bytes: bytes) -> Optional[demo_pb2.OrderResult]:
        """Parse protobuf OrderResult from Kafka message"""
        try:
            order = demo_pb2.OrderResult()
            order.ParseFromString(message_bytes)
            return order
        except Exception as e:
            logger.error(f"Failed to parse order protobuf: {e}")
            return None

    def _order_to_dict(self, order: demo_pb2.OrderResult) -> dict:
        """Convert OrderResult protobuf to dictionary for JSON serialization"""
        try:
            order_dict = {
                "order_id": order.order_id,
                "shipping_tracking_id": order.shipping_tracking_id,
                "shipping_cost": {
                    "currency_code": order.shipping_cost.currency_code,
                    "units": order.shipping_cost.units,
                    "nanos": order.shipping_cost.nanos
                },
                "shipping_address": {
                    "street_address": order.shipping_address.street_address,
                    "city": order.shipping_address.city,
                    "state": order.shipping_address.state,
                    "country": order.shipping_address.country,
                    "zip_code": order.shipping_address.zip_code
                },
                "items": []
            }

            # Add items
            for item in order.items:
                order_dict["items"].append({
                    "product_id": item.item.product_id,
                    "quantity": item.item.quantity,
                    "cost": {
                        "currency_code": item.cost.currency_code,
                        "units": item.cost.units,
                        "nanos": item.cost.nanos
                    }
                })

            return order_dict
        except Exception as e:
            logger.error(f"Failed to convert order to dict: {e}")
            return {}

    def _forward_to_lambda(self, order: demo_pb2.OrderResult) -> bool:
        """Forward order to AWS Lambda function"""

        with self.tracer.start_as_current_span("forward_to_lambda") as span:
            span.set_attribute("app.order.id", order.order_id)
            span.set_attribute("app.lambda.function", self.lambda_function_name)
            span.set_attribute("app.order.items_count", len(order.items))

            # Convert order to JSON
            order_dict = self._order_to_dict(order)
            payload = json.dumps(order_dict)

            span.set_attribute("app.payload.size_bytes", len(payload))

            try:
                start_time = time.time()

                # Invoke Lambda function
                response = self.lambda_client.invoke(
                    FunctionName=self.lambda_function_name,
                    InvocationType='Event',  # Async invocation
                    Payload=payload.encode('utf-8')
                )

                duration_ms = (time.time() - start_time) * 1000
                self.metrics["lambda_duration_histogram"].record(duration_ms)

                status_code = response.get('StatusCode', 0)
                span.set_attribute("app.lambda.status_code", status_code)

                if status_code in [200, 202]:
                    logger.info(f"Order {order.order_id} forwarded to Lambda successfully")
                    self.metrics["orders_forwarded_counter"].add(
                        1, {"status": "success", "lambda.function": self.lambda_function_name}
                    )
                    span.set_status(Status(StatusCode.OK))
                    return True
                else:
                    logger.error(f"Lambda returned status {status_code} for order {order.order_id}")
                    self.metrics["forwarding_errors_counter"].add(
                        1, {"error.type": "lambda_error", "status_code": str(status_code)}
                    )
                    span.set_status(Status(StatusCode.ERROR, f"Lambda error: {status_code}"))
                    return False

            except ClientError as e:
                error_code = e.response['Error']['Code']
                logger.error(f"AWS error forwarding order {order.order_id}: {error_code} - {e}")
                self.metrics["forwarding_errors_counter"].add(
                    1, {"error.type": "aws_client_error", "error.code": error_code}
                )
                span.set_status(Status(StatusCode.ERROR, f"AWS error: {error_code}"))
                span.record_exception(e)
                return False

            except Exception as e:
                logger.error(f"Error forwarding order {order.order_id} to Lambda: {e}")
                self.metrics["forwarding_errors_counter"].add(
                    1, {"error.type": "unknown_error"}
                )
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                return False

    def _log_order(self, order: demo_pb2.OrderResult):
        """Log order details (fallback when Lambda is not configured)"""
        with self.tracer.start_as_current_span("log_order") as span:
            span.set_attribute("app.order.id", order.order_id)
            span.set_attribute("app.order.items_count", len(order.items))

            order_dict = self._order_to_dict(order)
            logger.info(f"Order received: {json.dumps(order_dict, indent=2)}")

            self.metrics["orders_forwarded_counter"].add(
                1, {"status": "logged", "lambda.function": "none"}
            )

    def process_message(self, message):
        """
        Process a single Kafka message

        Extracts trace context from Kafka headers to link this span
        to the parent trace from the producer (checkout service).
        """

        # Extract trace context from Kafka message headers
        # This creates a parent-child relationship in the trace tree
        extracted_context = self._extract_trace_context(message)

        # Attach the extracted context and start span within that context
        # This makes the span a child of the producer's span
        ctx_token = context.attach(extracted_context)
        try:
            with self.tracer.start_as_current_span(
                "process_kafka_message",
                kind=trace.SpanKind.CONSUMER,
            ) as span:
                # Set Kafka semantic convention attributes
                span.set_attribute("messaging.system", "kafka")
                span.set_attribute("messaging.destination.name", message.topic)
                span.set_attribute("messaging.kafka.partition", message.partition)
                span.set_attribute("messaging.kafka.offset", message.offset)
                span.set_attribute("messaging.kafka.consumer.group", CONSUMER_GROUP_ID)
                span.set_attribute("messaging.operation", "receive")

                # Record Kafka message consumed
                self.metrics["kafka_messages_counter"].add(
                    1, {"kafka.topic": KAFKA_TOPIC}
                )

                # Parse order
                order = self._parse_order(message.value)
                if not order:
                    span.set_status(Status(StatusCode.ERROR, "Failed to parse order"))
                    self.total_errors += 1
                    return

                span.set_attribute("app.order.id", order.order_id)
                logger.info(f"Processing order: {order.order_id}")

                # Check if forwarding is disabled via feature flag
                if self._check_feature_flag("disableOrderForwarding", False):
                    logger.info(f"Order forwarding disabled by feature flag for order {order.order_id}")
                    span.set_attribute("app.forwarding.disabled", True)
                    return

                # Forward to Lambda or log
                if self.use_lambda:
                    success = self._forward_to_lambda(order)
                    if success:
                        self.total_forwarded += 1
                    else:
                        self.total_errors += 1
                else:
                    self._log_order(order)
                    self.total_forwarded += 1

                self.total_processed += 1

                # Log statistics every 100 orders
                if self.total_processed % 100 == 0:
                    logger.info(
                        f"Statistics: processed={self.total_processed}, "
                        f"forwarded={self.total_forwarded}, errors={self.total_errors}"
                    )
        finally:
            # Detach the context to clean up
            context.detach(ctx_token)

    def run(self):
        """Main consumer loop"""
        logger.info(f"Starting order analytics forwarder service")
        logger.info(f"Kafka broker: {self.kafka_address}")
        logger.info(f"Lambda function: {self.lambda_function_name if self.use_lambda else 'NOT CONFIGURED'}")
        logger.info(f"AWS region: {self.aws_region}")

        try:
            # Consume messages
            for message in self.consumer:
                try:
                    self.process_message(message)
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    self.total_errors += 1

        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
        except Exception as e:
            logger.error(f"Fatal error in consumer loop: {e}", exc_info=True)
            sys.exit(1)
        finally:
            self.consumer.close()
            logger.info(
                f"Final statistics: processed={self.total_processed}, "
                f"forwarded={self.total_forwarded}, errors={self.total_errors}"
            )


if __name__ == "__main__":
    # Ensure OTEL_SERVICE_NAME is set
    if not os.getenv("OTEL_SERVICE_NAME"):
        os.environ["OTEL_SERVICE_NAME"] = "order-analytics-forwarder"

    # Create and run forwarder
    forwarder = OrderAnalyticsForwarder()
    forwarder.run()
