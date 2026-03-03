# AWS Lambda Function for Order Analytics

Sample AWS Lambda function that receives and processes orders from the order-analytics-forwarder service.

## Overview

This Lambda function:
- Receives order data as JSON payloads
- Calculates analytics metrics (revenue, order size, geography)
- Can store data in DynamoDB, S3, or Kinesis
- Returns processing status

## Deployment Options

### Option 1: AWS Console (Quick Start)

1. **Create the Lambda function:**
   - Go to AWS Lambda console
   - Click "Create function"
   - Choose "Author from scratch"
   - Function name: `order-analytics-processor`
   - Runtime: Python 3.12
   - Click "Create function"

2. **Upload the code:**
   - Copy the contents of `lambda_function.py`
   - Paste into the Lambda code editor
   - Click "Deploy"

3. **Configure:**
   - Memory: 256 MB (adjust as needed)
   - Timeout: 30 seconds
   - Add environment variables if needed

4. **Set permissions:**
   - Add DynamoDB/S3/Kinesis permissions if using those services
   - The Lambda execution role needs `AWSLambdaBasicExecutionRole` at minimum

### Option 2: AWS CLI

```bash
# Create a deployment package
cd lambda-example
zip function.zip lambda_function.py

# Create the Lambda function
aws lambda create-function \
  --function-name order-analytics-processor \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-execution-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function.zip \
  --timeout 30 \
  --memory-size 256

# Update function code
aws lambda update-function-code \
  --function-name order-analytics-processor \
  --zip-file fileb://function.zip
```

### Option 3: Terraform

```hcl
resource "aws_lambda_function" "order_analytics" {
  filename      = "function.zip"
  function_name = "order-analytics-processor"
  role          = aws_iam_role.lambda_exec.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      DYNAMODB_TABLE = aws_dynamodb_table.order_analytics.name
      S3_BUCKET      = aws_s3_bucket.order_analytics.bucket
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name = "order-analytics-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
```

## Data Storage Options

The sample function includes commented examples for three storage options:

### Option 1: DynamoDB (Recommended for queryable analytics)

**Use case:** Fast queries, real-time dashboards

**Setup:**
1. Create a DynamoDB table:
```bash
aws dynamodb create-table \
  --table-name order-analytics \
  --attribute-definitions \
      AttributeName=order_id,AttributeType=S \
      AttributeName=timestamp,AttributeType=S \
  --key-schema \
      AttributeName=order_id,KeyType=HASH \
      AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
```

2. Add permissions to Lambda role:
```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:PutItem",
    "dynamodb:GetItem",
    "dynamodb:Query"
  ],
  "Resource": "arn:aws:dynamodb:*:*:table/order-analytics"
}
```

3. Uncomment `store_in_dynamodb()` in the Lambda function

### Option 2: S3 (Best for long-term storage and batch processing)

**Use case:** Data lake, historical analysis, cost-effective storage

**Setup:**
1. Create an S3 bucket:
```bash
aws s3 mb s3://order-analytics-bucket-YOUR_UNIQUE_ID
```

2. Add permissions to Lambda role:
```json
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject",
    "s3:GetObject"
  ],
  "Resource": "arn:aws:s3:::order-analytics-bucket-YOUR_UNIQUE_ID/*"
}
```

3. Uncomment `store_in_s3()` in the Lambda function

### Option 3: Kinesis Data Streams (Real-time streaming)

**Use case:** Real-time dashboards, downstream processing, event-driven architectures

**Setup:**
1. Create a Kinesis Data Stream:
```bash
aws kinesis create-stream \
  --stream-name order-analytics-stream \
  --shard-count 1
```

2. Add permissions to Lambda role:
```json
{
  "Effect": "Allow",
  "Action": [
    "kinesis:PutRecord",
    "kinesis:PutRecords"
  ],
  "Resource": "arn:aws:kinesis:*:*:stream/order-analytics-stream"
}
```

3. Uncomment `send_to_kinesis()` in the Lambda function

## Testing

### Test in AWS Console

1. Go to your Lambda function
2. Click "Test" tab
3. Create a new test event with this payload:

```json
{
  "order_id": "test-order-123",
  "shipping_tracking_id": "TRACK123",
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
      "product_id": "PROD-001",
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

4. Click "Test" and verify the function executes successfully

### Test with AWS CLI

```bash
aws lambda invoke \
  --function-name order-analytics-processor \
  --payload file://test-event.json \
  response.json

cat response.json
```

## Monitoring

### CloudWatch Logs

View function logs:
```bash
aws logs tail /aws/lambda/order-analytics-processor --follow
```

### CloudWatch Metrics

Monitor:
- Invocations
- Duration
- Errors
- Throttles

Create a CloudWatch dashboard for order analytics metrics.

### Alarms

Set up alarms for:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name order-analytics-errors \
  --alarm-description "Alert on Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --dimensions Name=FunctionName,Value=order-analytics-processor
```

## Configuration in order-analytics-forwarder

After deploying the Lambda function, configure the forwarder service:

### Kubernetes ConfigMap
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-analytics-config
data:
  LAMBDA_FUNCTION_NAME: "order-analytics-processor"
  AWS_REGION: "us-east-1"
```

### Update Deployment
```yaml
env:
- name: LAMBDA_FUNCTION_NAME
  valueFrom:
    configMapKeyRef:
      name: order-analytics-config
      key: LAMBDA_FUNCTION_NAME
- name: AWS_REGION
  valueFrom:
    configMapKeyRef:
      name: order-analytics-config
      key: AWS_REGION
```

## Cost Optimization

- **Lambda**: First 1M requests/month are free
- **DynamoDB**: Use on-demand pricing for variable workloads
- **S3**: Use lifecycle policies to transition old data to Glacier
- **Kinesis**: Consider Kinesis Data Firehose for direct S3 ingestion

## Extending the Function

### Add more analytics:
- Customer lifetime value calculation
- Fraud detection scoring
- Product recommendation generation
- Inventory impact analysis

### Integration examples:
- Send metrics to CloudWatch custom metrics
- Trigger SNS notifications for high-value orders
- Update Elasticsearch for search capabilities
- Send data to Redshift for data warehousing

## Troubleshooting

**Lambda times out:**
- Increase timeout setting
- Optimize database operations
- Use batch writes for DynamoDB

**Permission errors:**
- Check IAM role has necessary permissions
- Verify resource ARNs are correct
- Check VPC configuration if using private resources

**Data not appearing:**
- Check CloudWatch logs for errors
- Verify table/bucket names match
- Confirm AWS credentials in forwarder service

## License

Copyright The OpenTelemetry Authors
SPDX-License-Identifier: Apache-2.0
