# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

FROM docker.io/library/python:3.12-alpine3.22 AS build-venv

RUN apk update && \
    apk add gcc g++ linux-headers

COPY ./src/order-analytics-forwarder/requirements.txt requirements.txt

RUN python -m venv venv && \
    venv/bin/pip install --no-cache-dir -r requirements.txt

FROM docker.io/library/python:3.12-alpine3.22

COPY --from=build-venv /venv/ /venv/

WORKDIR /app

COPY ./src/order-analytics-forwarder/demo_pb2_grpc.py demo_pb2_grpc.py
COPY ./src/order-analytics-forwarder/demo_pb2.py demo_pb2.py
COPY ./src/order-analytics-forwarder/logger.py logger.py
COPY ./src/order-analytics-forwarder/metrics.py metrics.py
COPY ./src/order-analytics-forwarder/order_forwarder.py order_forwarder.py

# Use OpenTelemetry auto-instrumentation (provided by splunk-opentelemetry distribution)
ENTRYPOINT [ "/venv/bin/opentelemetry-instrument", "/venv/bin/python", "order_forwarder.py" ]
