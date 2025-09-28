# SMTP Server Architecture

## Overview

The SMTP server uses a decoupled, queue-based architecture designed for high availability and horizontal scaling in AWS VPC environments.

## Architecture Diagram

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐    ┌─────────────────┐
│ EC2/EKS         │    │ SMTP Server  │    │ S3 Bucket   │    │ Worker Process  │
│ Workloads       │───▶│              │───▶│ Full Email  │    │ Polls Queue     │
│                 │    │ Port 8025    │    │ Storage     │    │ Fetches from S3 │
└─────────────────┘    └──────────────┘    └─────────────┘    └─────────────────┘
                                                  │                       ▲
                                                  ▼                       │
┌─────────────────┐                       ┌─────────────┐                │
│ AWS SES         │                       │ SQS Queue   │────────────────┘
│ Incoming Email  │──────────────────────▶│ Metadata +  │
│                 │                       │ S3 Reference│
└─────────────────┘                       └─────────────┘
                                                  │
                                                  ▼
                                           ┌─────────────────────────────────────┐
                                           │ Final Processors                    │
                                           │ ┌─────────┐ ┌─────────┐ ┌─────────┐│
                                           │ │   S3    │ │   SES   │ │SMTP.com ││
                                           │ │Storage  │ │Forwarder│ │   API   ││
                                           │ └─────────┘ └─────────┘ └─────────┘│
                                           └─────────────────────────────────────┘
```

## Components

### 1. SMTP Server (`smtp_server.py`)

**Purpose**: Accept SMTP connections and queue emails for processing

**Key Features**:
- Async SMTP server using aiosmtpd
- Modular processor system
- Environment-based configuration
- Systemd integration with signal handling

**Flow**:
1. Accept SMTP connection
2. Receive email data
3. Parse envelope and message
4. Route through configured processors
5. Return SMTP response

## Message Flow Patterns

The system supports multiple email ingestion patterns:

### 1. Direct SMTP Pattern
```
Client → SMTP Server → SQS+S3 Hybrid → Worker → Final Processors
```

### 2. AWS SES Pattern  
```
AWS SES → S3 Storage → SQS Notification → Worker → Final Processors
```

### 3. Unified Processing
Both patterns use the same SQS queue and worker infrastructure for consistent processing.

## SQS Message Types

The worker automatically detects and handles two message formats:

### SMTP Server Messages
```json
{
  "id": "message-uuid",
  "envelope": {"mail_from": "...", "rcpt_tos": [...]},
  "s3_reference": {"bucket": "...", "key": "..."}
}
```

### SES Notifications
```json
{
  "Type": "Notification",
  "Message": "{\"eventType\":\"received\",\"mail\":{...},\"receipt\":{\"action\":{\"type\":\"S3\",\"bucketName\":\"...\",\"objectKey\":\"...\"}}}"
}
```

### 2. SQS Queue Processor (`processors/sqs_queue.py`)

**Purpose**: Queue emails to AWS SQS for async processing

**Message Format**:
```json
{
  "id": "uuid4",
  "timestamp": "2024-01-15T10:30:00Z",
  "envelope": {
    "mail_from": "sender@example.com",
    "rcpt_tos": ["recipient@example.com"]
  },
  "message": {
    "subject": "Email Subject",
    "from": "sender@example.com",
    "to": "recipient@example.com",
    "headers": {"X-Custom": "value"},
    "body": "Email body content",
    "raw": "Full RFC822 message"
  }
}
```

**Message Attributes**:
- `from_domain`: Sender domain for filtering
- `to_domain`: Recipient domain for filtering
- `message_id`: Unique message identifier

### 3. SQS Worker (`sqs_worker.py`)

**Purpose**: Process queued emails through final processors

**Key Features**:
- Long polling (20 seconds) for efficiency
- Batch processing (up to 10 messages)
- Message reconstruction from JSON
- Automatic message deletion on success
- Error handling and logging

**Flow**:
1. Poll SQS queue for messages
2. Parse JSON message body
3. Reconstruct EmailMessage object
4. Process through configured processors
5. Delete message on success

### 5. SQS+S3 Hybrid Processor (`processors/sqs_s3_hybrid.py`)

**Purpose**: Store complete emails in S3 and queue lightweight metadata in SQS

**Architecture Benefits**:
- No size limitations (handles large attachments)
- Fast SQS processing with lightweight messages
- Organized S3 storage with time-based structure
- Rich metadata for filtering and routing

**S3 Key Structure**:
```
emails/YYYY/MM/DD/HH/from_domain/message_id.eml
```

**SQS Message Format**:
```json
{
  "id": "uuid",
  "timestamp": "ISO8601",
  "envelope": {"mail_from": "...", "rcpt_tos": ["..."]},
  "headers": {"subject": "...", "from": "...", "to": "..."},
  "metadata": {
    "has_attachments": true,
    "is_multipart": true,
    "size_bytes": 2048576
  },
  "s3_reference": {
    "bucket": "bucket-name",
    "key": "emails/2024/01/15/10/example.com/uuid.eml"
  }
}
```

**Flow**:
1. Store complete email in S3 with structured key
2. Send lightweight metadata + S3 reference to SQS
3. Worker polls SQS, retrieves full email from S3
4. Process through final processors

### 6. Redis+Stream Hybrid Processor (`processors/redis_hybrid.py`)

**Purpose**: Store complete emails in Redis and queue lightweight metadata in Redis Streams

**Architecture Benefits**:
- Single backend system (no dependency on AWS services)
- Lower latency than S3-based storage
- Built-in TTL for automatic cleanup
- Atomic operations and strong consistency
- Better suited for on-premise or non-AWS deployments
- Support for distributed processing with consumer groups

**Redis Key Structure**:
```
email:message_id -> Hash with email data and metadata
```

**Redis Stream Message Format**:
```json
{
  "id": "uuid",
  "timestamp": "ISO8601",
  "envelope": {"mail_from": "...", "rcpt_tos": ["..."]},
  "headers": {"subject": "...", "from": "...", "to": "..."},
  "metadata": {
    "has_attachments": true,
    "is_multipart": true,
    "size_bytes": 2048576
  },
  "redis_reference": {
    "key": "email:uuid",
    "host": "redis-host",
    "port": 6379,
    "db": 0
  }
}
```

**Flow**:
1. Store complete email as Redis hash with TTL
2. Send lightweight metadata + Redis reference to Stream
3. Worker reads from Stream using consumer groups
4. Retrieve full email from Redis hash
5. Process through final processors
6. Acknowledge message in Stream

### 7. Redis Worker (`redis_worker.py`)

**Purpose**: Process queued emails from Redis Streams through final processors

**Key Features**:
- Redis Streams with consumer groups for reliable processing
- Automatic message acknowledgment on success
- Email reconstruction from Redis hash storage
- Support for multiple workers with load balancing
- Connection pooling and reconnection handling

**Flow**:
1. Read messages from Redis Stream (XREADGROUP)
2. Parse message payload
3. Retrieve complete email from Redis hash
4. Process through configured processors
5. Acknowledge message on success (XACK)

**Base Interface** (`base.py`):
```python
class EmailProcessor(ABC):
    @abstractmethod
    async def process(self, envelope, message: EmailMessage) -> bool:
        """Process email, return success status"""
        pass
```

**Available Processors**:
- `FileStorageProcessor`: Save emails to disk
- `S3StorageProcessor`: Store emails in AWS S3
- `SESForwarderProcessor`: Forward via AWS SES
- `SMTPComAPIProcessor`: Send via SMTP.com API
- `SQSQueueProcessor`: Queue to SQS for async processing
- `SQSS3HybridProcessor`: Store in S3 + queue metadata in SQS (recommended for AWS)
- `RedisHybridProcessor`: Store in Redis + queue metadata in Redis Streams (recommended for non-AWS)

## Configuration System

### Environment Variables

**SMTP Server**:
- `SMTP_HOST`: Bind address (default: 0.0.0.0)
- `SMTP_PORT`: Listen port (default: 8025)
- `LOG_LEVEL`: Logging level (default: INFO)

**SQS Integration**:
- `SQS_QUEUE_URL`: SQS queue URL for email processing
- `EMAIL_PROCESSORS`: JSON array of processor configurations

**Redis Worker Configuration (Dot-Notation)**:
- `worker.redis.stream_name`: Redis Stream name for email queue
- `worker.redis.host`: Redis server hostname (default: localhost)  
- `worker.redis.port`: Redis server port (default: 6379)
- `worker.redis.db`: Redis database number (default: 0)
- `worker.redis.password`: Redis authentication password (optional)
- `worker.redis.username`: Redis authentication username (optional)
- `worker.redis.ssl`: Enable SSL/TLS connection (default: false)
- `worker.redis.consumer_group`: Consumer group name (default: workers)
- `worker.redis.consumer_name`: Consumer name (auto-generated if not provided)

### Configuration Loading

1. Load from environment variables
2. Parse JSON processor configuration
3. Create processor instances with validation
4. Handle missing dependencies gracefully

### Example Configuration

```bash
# SMTP Server with SQS queuing
EMAIL_PROCESSORS=[{
  "type": "sqs_queue",
  "config": {
    "queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/email-queue"
  }
}]

# SMTP Server with Redis hybrid queuing
EMAIL_PROCESSORS=[{
  "type": "redis_hybrid",
  "config": {
    "redis_host": "localhost",
    "redis_port": 6379,
    "stream_name": "email_queue",
    "email_ttl": 86400
  }
}]

# Worker with multiple final processors
# (configured in worker code)
```

## Deployment Architecture

### Single Instance Deployment
```
┌─────────────────┐
│ EC2 Instance    │
│ ┌─────────────┐ │
│ │SMTP Server  │ │
│ └─────────────┘ │
│ ┌─────────────┐ │
│ │SQS Worker   │ │
│ └─────────────┘ │
└─────────────────┘
```

### Multi-Instance Deployment
```
┌─────────────────┐    ┌─────────────────┐
│ SMTP Servers    │    │ Worker Instances│
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │Instance 1   │ │    │ │Worker 1     │ │
│ └─────────────┘ │    │ └─────────────┘ │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │Instance 2   │ │───▶│ │Worker 2     │ │
│ └─────────────┘ │    │ └─────────────┘ │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │Instance N   │ │    │ │Worker N     │ │
│ └─────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └─────────────────┘
         │                       │
         └───────┐       ┌───────┘
                 ▼       ▼
         ┌─────────────────┐
         │   SQS Queue     │
         └─────────────────┘
```

## Scaling Strategies

### Horizontal Scaling

**SMTP Servers**:
- Deploy behind Network Load Balancer (TCP)
- Each instance writes to same SQS queue
- Scale based on connection count

**Workers**:
- Deploy multiple worker instances
- Each polls same SQS queue
- Scale based on queue depth

### Auto Scaling Triggers

**SMTP Servers**:
- CPU utilization > 70%
- Active connections > threshold
- Network I/O metrics

**Workers**:
- SQS queue depth > 100 messages
- Message age > 5 minutes
- Worker CPU utilization > 80%

## Security Considerations

### Network Security
- Deploy in private subnets
- Use VPC endpoints for AWS services
- Security groups restrict access to port 8025

### IAM Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:*:*:email-processing-queue"
    }
  ]
}
```

### Process Security
- Run as dedicated `smtp` user
- No shell access (`/bin/false`)
- Systemd security restrictions:
  - `NoNewPrivileges=true`
  - `PrivateTmp=true`
  - `ProtectSystem=strict`
  - `ProtectHome=true`

## Monitoring and Observability

### Logging
- Structured logging to stdout
- Journald integration
- Log levels: DEBUG, INFO, WARNING, ERROR

### Metrics (Planned)
- Prometheus exporter on separate port
- Key metrics:
  - `smtp_emails_received_total`
  - `smtp_queue_depth`
  - `smtp_processing_duration_seconds`
  - `smtp_processor_success_total`
  - `smtp_processor_failure_total`

### Health Checks
- SMTP server: TCP connection test on port 8025
- Worker: SQS queue polling status
- Processors: Individual health endpoints

## Error Handling

### SMTP Server Errors
- Invalid SMTP commands: Return appropriate SMTP error codes
- Processor failures: Log error, return 550 SMTP error
- Configuration errors: Fail fast on startup

### Worker Errors
- Message parsing errors: Log and delete invalid messages
- Processor failures: Retry with exponential backoff
- SQS errors: Retry with circuit breaker pattern

### Dead Letter Queues
- Configure SQS dead letter queue for failed messages
- Monitor DLQ depth for operational alerts
- Manual reprocessing workflow for DLQ messages

## Performance Characteristics

### Throughput
- SMTP Server: ~1000 concurrent connections
- SQS Queue: Unlimited buffering capacity
- Workers: ~100 messages/second per instance

### Latency
- SMTP Response: <100ms (queue only)
- End-to-end Processing: <5 seconds (depends on processors)
- Queue Polling: 20 second long polling

### Resource Usage
- SMTP Server: ~50MB RAM, minimal CPU
- Worker: ~100MB RAM, variable CPU (depends on processors)
- Network: Minimal (SQS API calls only)

## Future Enhancements

### Planned Features
1. Rule-based routing with AWS Parameter Store
2. Prometheus metrics with dimensional labels
3. Hot-reloadable configuration
4. Authentication mechanisms (PLAIN, LOGIN)
5. TLS/SSL support
6. Rate limiting per client/IP

### Architectural Improvements
1. Multi-AZ deployment with failover
2. VPC endpoint support
3. Container deployment (ECS/EKS)
4. Circuit breaker pattern for processors
5. Email deduplication
6. Batch processing optimization
