# API Documentation

## Rule-Based Email Routing

The system supports conditional email routing based on rules stored in AWS Parameter Store. This enables sophisticated email processing logic without code changes.

### Quick Start

1. **Enable Rule Engine**:
   ```bash
   RULE_ENGINE_PARAMETER=/email-routing/rules
   AWS_REGION=us-east-1
   ```

2. **Create Rules in Parameter Store**:
   ```bash
   aws ssm put-parameter \
     --name "/email-routing/rules" \
     --type "String" \
     --value "$(cat rules.json)"
   ```

3. **Basic Rule Example**:
   ```json
   {
     "rules": [
       {
         "name": "urgent_emails",
         "conditions": {"subject_contains": ["URGENT"]},
         "processors": ["smtpcom_priority"]
       }
     ],
     "processors": {
       "smtpcom_priority": {
         "type": "smtpcom_api",
         "api_key": "your-key",
         "channel": "priority"
       }
     }
   }
   ```

### Rule Processing

- **Sequential Evaluation**: Rules processed in array order
- **First Match Wins**: First matching rule determines processors  
- **Multiple Processors**: Single rule can trigger multiple processors
- **Default Rule**: Empty conditions `{}` match everything

### Matching Conditions

**Basic Matching**:
- `from_email` / `from_domain` - Sender matching
- `to_email` / `to_domain` - Recipient matching (any recipient)
- `subject_contains` - Subject text search
- `header_exists` / `header_value` - Header matching

**Advanced Matching** (Planned):
- Content analysis, time-based routing, regex patterns
- See [Rule Engine Roadmap](RULE_ENGINE_ROADMAP.md) for details

### Complete Documentation

For comprehensive rule engine documentation, see:
- **[Rule Engine Guide](RULE_ENGINE.md)** - Complete configuration and usage
- **[Rule Engine Roadmap](RULE_ENGINE_ROADMAP.md)** - Planned features and enhancements

## Configuration Format

Use dot-notation environment variables for processor configuration:

```bash
# Email processors for SMTP server
email.processors.0.type=smtpcom_api
email.processors.0.api_key=your-api-key
email.processors.0.channel=your-channel

# Worker processors for SQS worker
worker.processors.0.type=smtpcom_api
worker.processors.0.api_key=your-api-key
worker.processors.0.channel=your-channel

# Multiple processors
worker.processors.0.type=smtpcom_api
worker.processors.0.api_key=prod_key
worker.processors.0.channel=prod
worker.processors.1.type=ses_forwarder
worker.processors.1.region=us-east-1
worker.processors.1.from_email=noreply@domain.com

# Redis alternative to SQS+S3
email.processors.0.type=redis_hybrid
email.processors.0.redis_host=localhost
email.processors.0.stream_name=email_queue
email.processors.0.email_ttl=86400
```

## Processor Interface

All email processors implement the `EmailProcessor` base class.

### Base Class

```python
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Dict, Any

class EmailProcessor(ABC):
    """Base class for email processors"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize processor with configuration
        
        Args:
            config: Dictionary of processor-specific configuration
        """
        self.config = config or {}
    
    @abstractmethod
    async def process(self, envelope: Any, message: EmailMessage) -> bool:
        """
        Process an email message
        
        Args:
            envelope: SMTP envelope data with mail_from and rcpt_tos
            message: Parsed email message object
            
        Returns:
            bool: True if processing succeeded, False otherwise
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return processor name for logging"""
        pass
```

## Built-in Processors

### FileStorageProcessor

Stores emails as files on the local filesystem.

**Configuration**:
```bash
email.processors.0.type=file_storage
email.processors.0.storage_dir=/var/spool/mail
```

**Parameters**:
- `storage_dir` (string): Directory to store email files

**Behavior**:
- Creates timestamped `.eml` files
- Uses format: `YYYYMMDD_HHMMSS_microseconds.eml`
- Creates directory if it doesn't exist
- Writes full RFC822 message content

**Example**:
```python
processor = FileStorageProcessor({
    'storage_dir': '/var/spool/mail/inbox'
})
```

### S3StorageProcessor

Stores emails in AWS S3 buckets.

**Configuration**:
```json
{
  "type": "s3_storage",
  "config": {
    "bucket": "my-email-bucket",
    "prefix": "emails/"
  }
}
```

**Parameters**:
- `bucket` (string, required): S3 bucket name
- `prefix` (string, optional): Key prefix for stored emails

**Behavior**:
- Uses hierarchical key structure: `prefix/YYYY/MM/DD/HHMMSS_microseconds.eml`
- Sets `ContentType: message/rfc822`
- Requires appropriate IAM permissions

**IAM Permissions**:
```json
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject"
  ],
  "Resource": "arn:aws:s3:::my-email-bucket/*"
}
```

### SESForwarderProcessor

Forwards emails via AWS Simple Email Service.

**Configuration**:
```json
{
  "type": "ses_forwarder",
  "config": {
    "from_email": "noreply@example.com",
    "to_emails": ["admin@example.com", "alerts@example.com"]
  }
}
```

**Parameters**:
- `from_email` (string, required): Sender email address
- `to_emails` (array, required): List of recipient email addresses

**Behavior**:
- Sends raw email message via SES
- Preserves original message content and headers
- Requires verified sender domain in SES

**IAM Permissions**:
```json
{
  "Effect": "Allow",
  "Action": [
    "ses:SendRawEmail"
  ],
  "Resource": "*"
}
```

### SMTPComAPIProcessor

Sends emails via SMTP.com REST API with full attachment and encoding support.

**Configuration**:
```bash
email.processors.0.type=smtpcom_api
email.processors.0.api_key=your-smtp-com-api-key
email.processors.0.channel=your-channel-name
```

**Parameters**:
- `api_key` (string, required): SMTP.com API key
- `channel` (string, required): SMTP.com channel name for sending

**Behavior**:
- Extracts sender from email `From` header dynamically
- Converts email to SMTP.com API v4 format
- Uses proper authentication header (`X-SMTPCOM-API`)
- Sends via HTTPS POST to `https://api.smtp.com/v4/messages`
- Supports both text/plain and text/html content
- Handles attachments with proper base64 encoding
- Supports multiple character encodings (UTF-8, ISO-8859-1, etc.)
- 30-second request timeout
- Extracts plain text body from message

**API Format**:
```json
{
  "sender": "noreply@yourdomain.com",
  "recipients": ["recipient@example.com"],
  "subject": "Email Subject",
  "body": {
    "parts": [{
      "type": "text/plain",
      "content": "Email body content"
    }]
  }
}
```

### SQSQueueProcessor

Queues emails to AWS SQS for asynchronous processing.

**Configuration**:
```json
{
  "type": "sqs_queue",
  "config": {
    "queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/email-queue"
  }
}
```

**Parameters**:
- `queue_url` (string, required): Full SQS queue URL

**Behavior**:
- Serializes email data to JSON
- Adds message attributes for filtering
- Generates unique message ID (UUID4)
- Includes timestamp in ISO format

**Message Format**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00.123456Z",
  "envelope": {
    "mail_from": "sender@example.com",
    "rcpt_tos": ["recipient@example.com"]
  },
  "message": {
    "subject": "Email Subject",
    "from": "sender@example.com",
    "to": "recipient@example.com",
    "headers": {
      "Subject": "Email Subject",
      "From": "sender@example.com",
      "To": "recipient@example.com",
      "Date": "Mon, 15 Jan 2024 10:30:00 +0000"
    },
    "body": "Email body content",
    "raw": "Full RFC822 message including headers"
  }
}
```

**Message Attributes**:
- `from_domain` (String): Extracted sender domain
- `to_domain` (String): Extracted recipient domain  
- `message_id` (String): Unique message identifier

### SQSS3HybridProcessor

Stores complete emails in S3 and queues lightweight metadata in SQS (recommended for production).

**Configuration**:
```json
{
  "type": "sqs_s3_hybrid",
  "config": {
    "queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/email-queue",
    "s3_bucket": "my-email-storage-bucket",
    "s3_prefix": "emails/"
  }
}
```

**Parameters**:
- `queue_url` (string, required): Full SQS queue URL
- `s3_bucket` (string, required): S3 bucket name for email storage
- `s3_prefix` (string, optional): Key prefix for stored emails (default: "emails/")

**Behavior**:
- Stores complete email (including attachments) in S3
- Uses structured key: `emails/YYYY/MM/DD/HH/from_domain/message_id.eml`
- Sends lightweight metadata + S3 reference to SQS
- No size limitations (handles large attachments)
- Optimized for fast processing and organized storage

**S3 Key Structure**:
```
emails/
├── 2024/01/15/10/
│   ├── example.com/
│   │   ├── uuid1.eml
│   │   └── uuid2.eml
│   └── company.com/
│       └── uuid3.eml
```

**SQS Message Format**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:30:00.123456Z",
  "envelope": {
    "mail_from": "sender@example.com",
    "rcpt_tos": ["recipient@example.com"]
  },
  "headers": {
    "subject": "Email Subject",
    "from": "sender@example.com",
    "to": "recipient@example.com"
  },
  "metadata": {
    "has_attachments": true,
    "is_multipart": true,
    "size_bytes": 2048576
  },
  "s3_reference": {
    "bucket": "my-email-storage-bucket",
    "key": "emails/2024/01/15/10/example.com/550e8400-e29b-41d4-a716-446655440000.eml"
  }
}
```

**Message Attributes**:
- `from_domain` (String): Extracted sender domain
- `to_domain` (String): Extracted recipient domain
- `message_id` (String): Unique message identifier
- `has_attachments` (String): "true" if email has attachments
- `s3_bucket` (String): S3 bucket name
- `s3_key` (String): S3 object key

**IAM Permissions**:
```json
{
  "Effect": "Allow",
  "Action": [
    "sqs:SendMessage",
    "s3:PutObject"
  ],
  "Resource": [
    "arn:aws:sqs:*:*:email-processing-queue",
    "arn:aws:s3:::my-email-storage-bucket/*"
  ]
}
```

### RedisHybridProcessor

Stores complete emails in Redis and queues lightweight metadata in Redis Streams for processing by workers. Provides a single-backend alternative to SQS+S3 for non-AWS deployments.

**Configuration**:
```bash
email.processors.0.type=redis_hybrid
email.processors.0.redis_host=localhost
email.processors.0.redis_port=6379
email.processors.0.stream_name=email_queue
email.processors.0.email_ttl=86400
```

**Parameters**:
- `redis_host` (string, optional): Redis server hostname (default: localhost)
- `redis_port` (int, optional): Redis server port (default: 6379)
- `redis_db` (int, optional): Redis database number (default: 0)
- `redis_password` (string, optional): Redis authentication password
- `redis_username` (string, optional): Redis authentication username (Redis 6.0+)
- `redis_ssl` (bool, optional): Enable SSL/TLS connection (default: false)
- `stream_name` (string, optional): Redis Stream name for queue (default: email_queue)
- `email_ttl` (int, optional): Email storage TTL in seconds (default: 86400, 0 for no expiration)
- `key_prefix` (string, optional): Prefix for Redis keys (default: email:)

**Behavior**:
- Stores complete email as Redis hash with automatic TTL
- Sends lightweight metadata + Redis reference to Stream
- Uses Redis Streams for reliable queuing with consumer groups
- Supports distributed processing with multiple workers
- Lower latency than S3-based storage
- Built-in expiration for automatic cleanup

**Stream Message Format**:
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

**Stream Fields**:
- `message_id` (String): Unique message identifier
- `payload` (String): JSON-encoded message data
- `from_domain` (String): Extracted sender domain
- `to_domain` (String): Extracted recipient domain
- `has_attachments` (String): "true" if email has attachments
- `size_bytes` (String): Email size in bytes

**Example**:
```python
processor = RedisHybridProcessor({
    'redis_host': 'redis.example.com',
    'redis_port': 6379,
    'redis_password': 'secret',
    'stream_name': 'email_queue',
    'email_ttl': 7200  # 2 hours
})
```

## Creating Custom Processors

### Implementation Steps

1. **Inherit from EmailProcessor**:
```python
from processors.base import EmailProcessor

class CustomProcessor(EmailProcessor):
    def __init__(self, config=None):
        super().__init__(config)
        # Initialize custom configuration
        self.custom_setting = self.config.get('custom_setting', 'default')
```

2. **Implement Required Methods**:
```python
async def process(self, envelope, message: EmailMessage) -> bool:
    try:
        # Your processing logic here
        # Return True on success, False on failure
        return True
    except Exception as e:
        # Log error and return False
        return False

def get_name(self) -> str:
    return "CustomProcessor"
```

3. **Add to Factory Function**:
```python
# In smtp_server.py create_processors()
elif proc_type == 'custom':
    from processors import CustomProcessor
    processors.append(CustomProcessor(proc_settings))
```

4. **Update Module Exports**:
```python
# In processors/__init__.py
from .custom import CustomProcessor
__all__ = [..., 'CustomProcessor']
```

### Best Practices

**Error Handling**:
- Always return boolean success status
- Log errors with context
- Don't raise exceptions from `process()` method

**Configuration**:
- Validate required configuration in `__init__()`
- Provide sensible defaults
- Raise `ValueError` for invalid configuration

**Async Operations**:
- Use `asyncio.to_thread()` for blocking operations
- Don't block the event loop
- Handle timeouts appropriately

**Resource Management**:
- Initialize connections in `__init__()`
- Reuse connections across calls
- Implement cleanup if needed

### Example Custom Processor

```python
import asyncio
import aiohttp
from processors.base import EmailProcessor

class WebhookProcessor(EmailProcessor):
    """Send email notifications via webhook"""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.webhook_url = self.config.get('webhook_url')
        self.timeout = self.config.get('timeout', 30)
        
        if not self.webhook_url:
            raise ValueError("webhook_url required")
    
    async def process(self, envelope, message) -> bool:
        try:
            payload = {
                'from': envelope.mail_from,
                'to': envelope.rcpt_tos,
                'subject': message.get('Subject', ''),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    return response.status == 200
                    
        except Exception:
            return False
    
    def get_name(self) -> str:
        return "WebhookProcessor"
```

## Configuration Reference

### Environment Variables

**SMTP Server**:
- `SMTP_HOST`: Server bind address (default: "0.0.0.0")
- `SMTP_PORT`: Server port (default: 8025)
- `LOG_LEVEL`: Logging level (default: "INFO")

**SQS Integration**:
- `SQS_QUEUE_URL`: SQS queue URL for worker

### Processor Configuration Format

Processors are configured using dot-notation environment variables:

```bash
# Single processor
email.processors.0.type=processor_type
email.processors.0.parameter1=value1
email.processors.0.parameter2=value2

# Redis hybrid processor example
email.processors.0.type=redis_hybrid
email.processors.0.redis_host=redis.example.com
email.processors.0.redis_port=6379
email.processors.0.redis_db=0
email.processors.0.redis_password=secret_password
email.processors.0.redis_username=redis_user
email.processors.0.redis_ssl=true
email.processors.0.stream_name=email_queue
email.processors.0.email_ttl=86400
email.processors.0.key_prefix=email:

# Redis worker configuration (for redis_worker.py)
worker.redis.stream_name=email_queue
worker.redis.host=localhost
worker.redis.port=6379
worker.redis.db=0
worker.redis.password=secret_password
worker.redis.username=redis_user
worker.redis.ssl=true
worker.redis.consumer_group=workers
worker.redis.consumer_name=worker-1

# Multiple processors with Redis
email.processors.0.type=redis_hybrid
email.processors.0.redis_host=localhost
email.processors.0.stream_name=email_queue
email.processors.0.email_ttl=7200
email.processors.1.type=file_storage
email.processors.1.storage_dir=/backup/emails

# SQS+S3 alternative comparison
email.processors.0.type=sqs_s3_hybrid
email.processors.0.queue_url=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue
email.processors.0.s3_bucket=my-email-storage
email.processors.0.s3_prefix=emails/
```

### Multiple Processors

Emails are processed through all configured processors sequentially.

## Error Codes and Responses

### SMTP Response Codes

**Success**:
- `250 Message accepted`: Email successfully processed by all processors
- `250 OK`: RCPT TO command accepted

**Errors**:
- `550 Error processing message`: One or more processors failed
- `421 Service not available`: Server shutting down or overloaded
- `500 Command not recognized`: Invalid SMTP command

### Processor Return Values

- `True`: Processing succeeded
- `False`: Processing failed (logged but doesn't stop other processors)
- `Exception`: Caught and treated as failure

### Logging Levels

**INFO**: Normal operations
- Server start/stop
- Email received/processed
- Processor success

**WARNING**: Recoverable errors
- Processor failures
- Configuration issues
- Temporary service unavailability

**ERROR**: Serious errors
- Server startup failures
- Configuration validation errors
- Unhandled exceptions

**DEBUG**: Detailed information
- SMTP protocol details
- Message content (sanitized)
- Processor configuration
