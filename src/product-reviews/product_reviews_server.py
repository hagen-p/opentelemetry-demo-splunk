#!/usr/bin/python

# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


# Python
import os
import json
from concurrent import futures
import random
import sys

# Pip
import grpc
from opentelemetry import trace, metrics, context
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Status, StatusCode

# Local
import logging
import demo_pb2
import demo_pb2_grpc
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc
from database import fetch_product_reviews, fetch_product_reviews_from_db, fetch_avg_product_review_score_from_db

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

from metrics import (
    init_metrics
)

# LangChain
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import tool as langchain_tool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from google.protobuf.json_format import MessageToJson, MessageToDict

llm_host = None
llm_port = None
llm_mock_url = None
llm_base_url = None
llm_api_key = None
llm_model = None

# Global variables for gRPC stub (initialized in main)
product_catalog_stub = None

# --- Define LangChain tools ---
@langchain_tool
def fetch_product_reviews_tool(product_id: str) -> str:
    """Executes a SQL query to retrieve reviews for a particular product.

    Args:
        product_id: The product ID to fetch product reviews for.

    Returns:
        JSON string containing the product reviews.
    """
    return fetch_product_reviews(product_id=product_id)

@langchain_tool
def fetch_product_info_tool(product_id: str) -> str:
    """Retrieves information for a particular product.

    Args:
        product_id: The product ID to fetch information for.

    Returns:
        JSON string containing the product information.
    """
    return fetch_product_info(product_id=product_id)

class ProductReviewService(demo_pb2_grpc.ProductReviewServiceServicer):
    def GetProductReviews(self, request, context):
        logger.info(f"Receive GetProductReviews for product id:{request.product_id}")
        product_reviews = get_product_reviews(request.product_id)

        return product_reviews

    def GetAverageProductReviewScore(self, request, context):
        logger.info(f"Receive GetAverageProductReviewScore for product id:{request.product_id}")
        product_reviews = get_average_product_review_score(request.product_id)

        return product_reviews

    def AskProductAIAssistant(self, request, context):
        logger.info(f"Receive AskProductAIAssistant for product id:{request.product_id}, question: {request.question}")
        ai_assistant_response = get_ai_assistant_response(request.product_id, request.question)

        return ai_assistant_response

    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING)

    def Watch(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.UNIMPLEMENTED)

def get_product_reviews(request_product_id):

    with tracer.start_as_current_span("get_product_reviews") as span:

        span.set_attribute("app.product.id", request_product_id)

        product_reviews = demo_pb2.GetProductReviewsResponse()
        records = fetch_product_reviews_from_db(request_product_id)

        for row in records:
            logger.info(f"  username: {row[0]}, description: {row[1]}, score: {str(row[2])}")
            product_reviews.product_reviews.add(
                    username=row[0],
                    description=row[1],
                    score=str(row[2])
            )

        span.set_attribute("app.product_reviews.count", len(product_reviews.product_reviews))

        # Collect metrics for this service
        product_review_svc_metrics["app_product_review_counter"].add(len(product_reviews.product_reviews), {'product.id': request_product_id})

        return product_reviews

def get_average_product_review_score(request_product_id):

    with tracer.start_as_current_span("get_average_product_review_score") as span:

        span.set_attribute("app.product.id", request_product_id)

        product_review_score = demo_pb2.GetAverageProductReviewScoreResponse()
        avg_score = fetch_avg_product_review_score_from_db(request_product_id)
        product_review_score.average_score = avg_score

        span.set_attribute("app.product_reviews.average_score", avg_score)

        return product_review_score

def get_ai_assistant_response(request_product_id, question):

    with tracer.start_as_current_span("get_ai_assistant_response") as span:

        ai_assistant_response = demo_pb2.AskProductAIAssistantResponse()

        span.set_attribute("app.product.id", request_product_id)
        span.set_attribute("app.product.question", question)

        # Check feature flags
        llm_rate_limit_error = check_feature_flag("llmRateLimitError")
        llm_inaccurate_response = check_feature_flag("llmInaccurateResponse")

        logger.info(f"llmRateLimitError feature flag: {llm_rate_limit_error}")
        logger.info(f"llmInaccurateResponse feature flag: {llm_inaccurate_response}")

        # Handle rate limit error simulation (50% chance)
        if llm_rate_limit_error:
            random_number = random.random()
            logger.info(f"Generated a random number: {str(random_number)}")
            if random_number < 0.5:
                logger.info(f"Simulating rate limit error with model: astronomy-llm-rate-limit")

                try:
                    # Use mock LLM to trigger 429 error
                    llm = ChatOpenAI(
                        base_url=llm_mock_url,
                        api_key=llm_api_key,
                        model="astronomy-llm-rate-limit",
                        temperature=0
                    )

                    # Attempt to invoke (will fail with 429)
                    prompt = ChatPromptTemplate.from_messages([
                        ("system", "You are a helpful assistant that answers related to a specific product. "
                                  "Use tools as needed to fetch the product reviews and product information. "
                                  "Keep the response brief with no more than 1-2 sentences. "
                                  "If you don't know the answer, just say you don't know."),
                        ("user", "Answer the following question about product ID:{product_id}: {question}"),
                        MessagesPlaceholder(variable_name="agent_scratchpad"),
                    ])

                    tools = [fetch_product_reviews_tool, fetch_product_info_tool]
                    agent = create_tool_calling_agent(llm, tools, prompt)
                    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

                    result = agent_executor.invoke({
                        "product_id": request_product_id,
                        "question": question
                    })

                except Exception as e:
                    logger.error(f"Caught Exception: {e}")
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, description=str(e)))
                    ai_assistant_response.response = "The system is unable to process your response. Please try again later."
                    return ai_assistant_response

        # Normal processing with LangChain
        try:
            logger.info(f"Creating LangChain agent with model: {llm_model}")

            # Create LLM
            llm = ChatOpenAI(
                base_url=llm_base_url,
                api_key=llm_api_key,
                model=llm_model,
                temperature=0
            )

            # Modify system prompt based on inaccurate response flag
            if llm_inaccurate_response and request_product_id == "L9ECAV7KIM":
                logger.info(f"Using inaccurate response mode for product_id: {request_product_id}")
                system_message = (
                    "You are a helpful assistant that answers related to a specific product. "
                    "Use tools as needed to fetch the product reviews and product information. "
                    "Based on the tool results, provide an INACCURATE answer to the question. "
                    "Keep the response brief with no more than 1-2 sentences."
                )
            else:
                system_message = (
                    "You are a helpful assistant that answers related to a specific product. "
                    "Use tools as needed to fetch the product reviews and product information. "
                    "Keep the response brief with no more than 1-2 sentences. "
                    "If you don't know the answer, just say you don't know."
                )

            # Create prompt template
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_message),
                ("user", "Answer the following question about product ID:{product_id}: {question}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])

            # Create agent with tools
            tools = [fetch_product_reviews_tool, fetch_product_info_tool]
            agent = create_tool_calling_agent(llm, tools, prompt)
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                return_intermediate_steps=True
            )

            logger.info(f"Invoking LangChain agent for product_id: {request_product_id}")

            # Execute agent
            result = agent_executor.invoke({
                "product_id": request_product_id,
                "question": question
            })

            # Extract output from result
            output = result.get("output", "")
            logger.info(f"LangChain agent returned: '{output}'")

            # Log intermediate steps (tool calls) for debugging
            if "intermediate_steps" in result:
                for i, (action, observation) in enumerate(result["intermediate_steps"]):
                    logger.info(f"Tool call {i+1}: {action.tool} with args {action.tool_input}")
                    logger.info(f"Tool response {i+1}: {observation[:200]}...")  # Truncate long responses

            ai_assistant_response.response = output

        except Exception as e:
            logger.error(f"Error in LangChain agent execution: {e}")
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, description=str(e)))
            ai_assistant_response.response = "I encountered an error processing your question. Please try again."
            return ai_assistant_response

        # Collect metrics for this service
        product_review_svc_metrics["app_ai_assistant_counter"].add(1, {'product.id': request_product_id})

        return ai_assistant_response

def fetch_product_info(product_id):
    try:
        product = product_catalog_stub.GetProduct(demo_pb2.GetProductRequest(id=product_id))
        logger.info(f"product_catalog_stub.GetProduct returned: '{product}'")
        json_str = MessageToJson(product)
        return json_str
    except Exception as e:
        return json.dumps({"error": str(e)})

def must_map_env(key: str):
    value = os.environ.get(key)
    if value is None:
        raise Exception(f'{key} environment variable must be set')
    return value

def check_feature_flag(flag_name: str):
    # Initialize OpenFeature
    client = api.get_client()
    return client.get_boolean_value(flag_name, False)

class SplunkHECJsonFormatter(logging.Formatter):
    """
    Custom JSON formatter for Splunk HEC with OpenTelemetry trace context
    """
    def format(self, record):
        # Get trace context from current span
        span = trace.get_current_span()
        span_context = span.get_span_context()

        log_data = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'source': {
                'file': record.pathname,
                'line': record.lineno,
                'function': record.funcName
            }
        }

        # Add trace context if available
        if span_context.is_valid:
            log_data['trace_id'] = format(span_context.trace_id, '032x')
            log_data['span_id'] = format(span_context.span_id, '016x')
            log_data['trace_flags'] = span_context.trace_flags

        # Add service name from resource
        if hasattr(record, 'otelServiceName'):
            log_data['service.name'] = record.otelServiceName

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data)

if __name__ == "__main__":
    service_name = must_map_env('OTEL_SERVICE_NAME')

    api.set_provider(FlagdProvider(host=os.environ.get('FLAGD_HOST', 'flagd'), port=os.environ.get('FLAGD_PORT', 8013)))

    # Initialize Traces and Metrics
    tracer = trace.get_tracer_provider().get_tracer(service_name)
    meter = metrics.get_meter_provider().get_meter(service_name)

    product_review_svc_metrics = init_metrics(meter)

    # Initialize Logs
    # Check if LoggerProvider is already set (by auto-instrumentation)
    from opentelemetry._logs import get_logger_provider, NoOpLoggerProvider

    existing_provider = get_logger_provider()
    if isinstance(existing_provider, NoOpLoggerProvider):
        # No provider set yet, create one
        logger_provider = LoggerProvider(
            resource=Resource.create(
                {
                    'service.name': service_name,
                }
            ),
        )
        set_logger_provider(logger_provider)
        log_exporter = OTLPLogExporter(insecure=True)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

        # Create OTLP handler (for sending to collector)
        otlp_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    else:
        # Provider already exists (from auto-instrumentation), use it
        otlp_handler = LoggingHandler(level=logging.NOTSET, logger_provider=existing_provider)

    # Create console handler with JSON formatter (for stdout/Splunk HEC)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    json_formatter = SplunkHECJsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S.%fZ'
    )
    console_handler.setFormatter(json_formatter)

    # Attach handlers to logger
    # Only add console handler (for JSON output to stdout)
    # OTLP handler sends to collector via gRPC (not stdout)
    logger = logging.getLogger('main')
    logger.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    # Note: OTLP handler is attached via opentelemetry auto-instrumentation

    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # Add class to gRPC server
    service = ProductReviewService()
    demo_pb2_grpc.add_ProductReviewServiceServicer_to_server(service, server)
    health_pb2_grpc.add_HealthServicer_to_server(service, server)

    llm_host = must_map_env('LLM_HOST')
    llm_port = must_map_env('LLM_PORT')
    llm_mock_url = f"http://{llm_host}:{llm_port}/v1"
    llm_base_url = must_map_env('LLM_BASE_URL')
    llm_api_key = must_map_env('OPENAI_API_KEY')
    llm_model = must_map_env('LLM_MODEL')

    catalog_addr = must_map_env('PRODUCT_CATALOG_ADDR')
    pc_channel = grpc.insecure_channel(catalog_addr)
    product_catalog_stub = demo_pb2_grpc.ProductCatalogServiceStub(pc_channel)

    # Start server
    port = must_map_env('PRODUCT_REVIEWS_PORT')
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info(f'Product reviews service started, listening on port {port}')
    server.wait_for_termination()
