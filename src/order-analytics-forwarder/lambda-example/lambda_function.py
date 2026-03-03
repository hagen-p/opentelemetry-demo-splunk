#!/usr/bin/env python3
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
AWS Lambda function for processing orders from order-analytics-forwarder

This is a sample implementation that demonstrates how to:
1. Receive order data from the forwarder
2. Process and transform the data
3. Store analytics in DynamoDB, S3, or other AWS services
4. Return processing status

Deploy this function to AWS Lambda and configure the order-analytics-forwarder
service to use it by setting LAMBDA_FUNCTION_NAME environment variable.
"""

import json
import logging
from datetime import datetime
from decimal import Decimal

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Main Lambda handler function

    Args:
        event: Order data sent from order-analytics-forwarder
        context: Lambda execution context

    Returns:
        dict: Processing status and metadata
    """

    logger.info(f"Received order analytics event")
    logger.info(f"Event: {json.dumps(event, indent=2)}")

    try:
        # Parse order data
        order_id = event.get('order_id', 'unknown')
        items = event.get('items', [])
        shipping_address = event.get('shipping_address', {})
        shipping_cost = event.get('shipping_cost', {})

        logger.info(f"Processing order: {order_id}")

        # Calculate order analytics
        analytics = calculate_order_analytics(event)

        # Store analytics (example - adapt to your needs)
        # store_in_dynamodb(analytics)
        # store_in_s3(analytics)
        # send_to_kinesis(analytics)

        # For now, just log the analytics
        logger.info(f"Order analytics: {json.dumps(analytics, indent=2, default=str)}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Order processed successfully',
                'order_id': order_id,
                'analytics': analytics
            }, default=str)
        }

    except Exception as e:
        logger.error(f"Error processing order: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'Failed to process order'
            })
        }


def calculate_order_analytics(order):
    """Calculate analytics metrics from order data"""

    items = order.get('items', [])
    shipping_cost = order.get('shipping_cost', {})
    shipping_address = order.get('shipping_address', {})

    # Calculate total items and revenue
    total_items = sum(item.get('quantity', 0) for item in items)
    total_product_cost = sum(
        money_to_decimal(item.get('cost', {})) * item.get('quantity', 0)
        for item in items
    )

    shipping_cost_decimal = money_to_decimal(shipping_cost)
    total_revenue = total_product_cost + shipping_cost_decimal

    # Extract product analytics
    product_ids = [item.get('product_id') for item in items]
    product_quantities = {
        item.get('product_id'): item.get('quantity', 0)
        for item in items
    }

    # Geographic analytics
    country = shipping_address.get('country', 'unknown')
    state = shipping_address.get('state', 'unknown')
    city = shipping_address.get('city', 'unknown')

    analytics = {
        'order_id': order.get('order_id'),
        'timestamp': datetime.utcnow().isoformat(),
        'metrics': {
            'total_items': total_items,
            'unique_products': len(product_ids),
            'total_product_cost': float(total_product_cost),
            'shipping_cost': float(shipping_cost_decimal),
            'total_revenue': float(total_revenue),
            'currency': shipping_cost.get('currency_code', 'USD')
        },
        'products': {
            'product_ids': product_ids,
            'quantities': product_quantities
        },
        'geography': {
            'country': country,
            'state': state,
            'city': city
        },
        'dimensions': {
            # Useful for analytics aggregations
            'country': country,
            'has_international_shipping': country != 'US',
            'order_size_category': categorize_order_size(total_items),
            'revenue_category': categorize_revenue(float(total_revenue))
        }
    }

    return analytics


def money_to_decimal(money):
    """Convert protobuf Money message to Decimal"""
    if not money:
        return Decimal('0')

    units = money.get('units', 0)
    nanos = money.get('nanos', 0)

    # Combine units and nanos
    return Decimal(units) + Decimal(nanos) / Decimal('1000000000')


def categorize_order_size(total_items):
    """Categorize order by number of items"""
    if total_items == 1:
        return 'single'
    elif total_items <= 3:
        return 'small'
    elif total_items <= 6:
        return 'medium'
    else:
        return 'large'


def categorize_revenue(total_revenue):
    """Categorize order by revenue"""
    if total_revenue < 20:
        return 'low'
    elif total_revenue < 50:
        return 'medium'
    elif total_revenue < 100:
        return 'high'
    else:
        return 'premium'


# Example: Store in DynamoDB
def store_in_dynamodb(analytics):
    """
    Store analytics in DynamoDB table

    Uncomment and configure to use:
    1. Create a DynamoDB table (e.g., 'order-analytics')
    2. Grant Lambda execution role permissions to write to the table
    3. Install boto3 (included in Lambda runtime)
    """
    # import boto3
    #
    # dynamodb = boto3.resource('dynamodb')
    # table = dynamodb.Table('order-analytics')
    #
    # # Convert floats to Decimal for DynamoDB
    # from decimal import Decimal
    # analytics_decimal = json.loads(
    #     json.dumps(analytics),
    #     parse_float=Decimal
    # )
    #
    # table.put_item(Item=analytics_decimal)
    # logger.info(f"Stored analytics in DynamoDB for order {analytics['order_id']}")
    pass


# Example: Store in S3
def store_in_s3(analytics):
    """
    Store analytics in S3 bucket as JSON

    Uncomment and configure to use:
    1. Create an S3 bucket (e.g., 'order-analytics-bucket')
    2. Grant Lambda execution role permissions to write to the bucket
    """
    # import boto3
    # from datetime import datetime
    #
    # s3 = boto3.client('s3')
    # bucket_name = 'order-analytics-bucket'
    #
    # # Organize by date for easier querying
    # today = datetime.utcnow()
    # key = f"orders/{today.year}/{today.month:02d}/{today.day:02d}/{analytics['order_id']}.json"
    #
    # s3.put_object(
    #     Bucket=bucket_name,
    #     Key=key,
    #     Body=json.dumps(analytics, indent=2, default=str),
    #     ContentType='application/json'
    # )
    # logger.info(f"Stored analytics in S3: s3://{bucket_name}/{key}")
    pass


# Example: Send to Kinesis Data Stream
def send_to_kinesis(analytics):
    """
    Send analytics to Kinesis Data Stream for real-time processing

    Uncomment and configure to use:
    1. Create a Kinesis Data Stream (e.g., 'order-analytics-stream')
    2. Grant Lambda execution role permissions to put records
    """
    # import boto3
    #
    # kinesis = boto3.client('kinesis')
    # stream_name = 'order-analytics-stream'
    #
    # kinesis.put_record(
    #     StreamName=stream_name,
    #     Data=json.dumps(analytics, default=str),
    #     PartitionKey=analytics['order_id']
    # )
    # logger.info(f"Sent analytics to Kinesis stream: {stream_name}")
    pass
