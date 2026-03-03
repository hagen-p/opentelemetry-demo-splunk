#!/usr/bin/env python
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
from pythonjsonlogger import jsonlogger
from opentelemetry import trace

class JsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that adds OpenTelemetry trace context"""

    def add_fields(self, log_record, record, message_dict):
        super(JsonFormatter, self).add_fields(log_record, record, message_dict)

        # Add OpenTelemetry trace context
        span = trace.get_current_span()
        span_context = span.get_span_context()

        if span_context.is_valid:
            log_record['trace_id'] = format(span_context.trace_id, '032x')
            log_record['span_id'] = format(span_context.span_id, '016x')
            log_record['trace_flags'] = span_context.trace_flags

def setup_logger(name):
    """Setup logger with JSON formatting and OTel context"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    formatter = JsonFormatter(
        '%(timestamp)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] '
        '[trace_id=%(trace_id)s span_id=%(span_id)s] - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
