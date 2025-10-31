# Q&A: Redis Stream Processor Configuration

This document contains questions and answers about the Redis Stream Processor implementation (after refactoring from `redis_hybrid` to `redis_stream`).

## Deployment and Configuration

### Q: I am deploying this on non-aws environment. I want to use redis as the message queue between smtp server and the workers. My redis instance is on host 192.168.1.11. What would the env config file look like for the smtp server process?

**A:** For your non-AWS environment with Redis at `192.168.1.11`, your `.env` file for the SMTP server process would look like this:

```bash
# =============================================================================
# SMTP SERVER CONFIGURATION
# =============================================================================
SMTP_HOST=0.0.0.0
SMTP_PORT=8025
LOG_LEVEL=INFO

# =============================================================================
# REDIS STREAM PROCESSOR - SMTP Server Configuration
# =============================================================================
email.processors.0.type=redis_stream
email.processors.0.redis_host=192.168.1.11
email.processors.0.redis_port=6379
email.processors.0.redis_db=0
email.processors.0.stream_name=email_queue
email.processors.0.email_ttl=86400
```

This configures the SMTP server to:
- Listen on all interfaces (`0.0.0.0:8025`)
- Use the `RedisStreamProcessor` to store emails in Redis hashes and queue metadata in Redis Streams
- Connect to your Redis instance at `192.168.1.11:6379`
- Use the default database (0) with a 24-hour TTL for stored emails
- Queue messages to the `email_queue` Redis Stream for worker processing

The workers would then consume from this same Redis Stream to process the emails.

### Q: I want to use redis as the queue mechanisam, but use filesystem for storage of the email objects, what would my smtp server env configuration look like?

**A:** That is not currently supported. The `RedisStreamProcessor` is designed as an integrated Redis-based solution that stores emails in Redis hashes and queues metadata in Redis Streams. It cannot be configured to use Redis for queuing while storing emails on the filesystem. 

The current processors follow these patterns:
- `RedisStreamProcessor`: Uses Redis for both storage AND queuing
- `FileStorageProcessor`: Uses filesystem for storage only (no queuing)
- `SQSS3HybridProcessor`: Uses S3 for storage and SQS for queuing

To achieve Redis-queue-only with filesystem storage, you would need either a custom processor or architectural changes to separate the queuing mechanism from the storage mechanism in the Redis implementation.

### Q: What are all of our current processor methods?

**A:** The current processor methods available in the system are:

**Storage-Only Processors:**
- `file_storage` (`FileStorageProcessor`): Stores emails as files on the local filesystem
- `s3_storage` (`S3StorageProcessor`): Stores emails in AWS S3 buckets

**Queue-Only Processors:**
- `sqs_queue` (`SQSQueueProcessor`): Queues emails to AWS SQS for asynchronous processing

**Forwarding Processors:**
- `ses_forwarder` (`SESForwarderProcessor`): Forwards emails via AWS Simple Email Service
- `smtpcom_api` (`SMTPComAPIProcessor`): Sends emails via SMTP.com REST API

**Integrated Processors (Storage + Queue):**
- `sqs_s3_hybrid` (`SQSS3HybridProcessor`): Stores complete emails in S3 and queues lightweight metadata in SQS (recommended for AWS deployments)
- `redis_stream` (`RedisStreamProcessor`): Stores complete emails in Redis hashes and queues lightweight metadata in Redis Streams (recommended for non-AWS deployments)

Each processor type serves different use cases:
- **Storage processors** save emails for archival/backup
- **Queue processors** enable asynchronous worker processing  
- **Forwarding processors** deliver emails to external services
- **Integrated processors** provide complete queued processing solutions

### Q: I want to use the SQSQueueProcessor and FileStorageProcessor so i can have async queue processing and filesystem based storage for the email object being processed, what would my smtp server env config look like?

**A:** That specific combination doesn't achieve your intended workflow. While you can configure both `FileStorageProcessor` and `SQSQueueProcessor` together, the SQS workers will process the complete email data from the SQS messages, not from the filesystem storage. The filesystem copies become redundant backups rather than the primary storage for worker processing.

To achieve filesystem-based storage with SQS queuing, you would need either:
- **A custom processor** that stores emails to filesystem and queues only file references to SQS
- **Use `sqs_s3_hybrid` instead**, which stores emails in S3 and queues lightweight metadata - this achieves your intended separation of storage and queuing but uses S3 instead of filesystem

The current architecture doesn't support filesystem storage with SQS-based worker processing that uses those filesystem files.

### Q: What are the differences between the queued message metadata/content for the sqs s3 hybrid vs the redis stream?

**A:** Both hybrid processors use similar lightweight metadata approaches, but there are key differences in the queue message structure:

**SQS+S3 Hybrid Message Structure:**
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
    "key": "emails/2024/01/15/10/example.com/550e8400.eml"
  }
}
```

**Redis Stream Message Structure:**
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
  "redis_reference": {
    "key": "email:550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Key Differences:**
- **Storage Reference**: SQS uses `s3_reference` with bucket/key, Redis uses `redis_reference` with just the Redis key
- **Queue Location**: SQS messages stored in AWS SQS, Redis messages stored in Redis Streams
- **Worker Retrieval**: SQS workers call S3 APIs, Redis workers use Redis hash commands on their configured Redis instance
- **Infrastructure**: SQS+S3 requires two AWS services, Redis uses single Redis instance

**Similarities:**
- Both queue lightweight metadata only (not full email content)
- Both include envelope, headers, and email metadata
- Both use references to retrieve full email content during processing

### Q: How is this value generated? "id": "550e8400-e29b-41d4-a716-446655440000"

**A:** This is a UUID4 (Universally Unique Identifier version 4) that is automatically generated by both the `SQSS3HybridProcessor` and `RedisStreamProcessor` for each email processed.

**Generation Process:**
- Uses Python's `uuid.uuid4()` function to create a random 128-bit identifier
- Format: 8-4-4-4-12 hexadecimal digits (32 characters total with dashes)
- Generated when the processor handles each incoming email
- Serves as the unique identifier for that specific email throughout the system

**Usage:**
- **SQS+S3 Hybrid**: Used as part of the S3 object key (`emails/2024/01/15/10/example.com/550e8400-e29b-41d4-a716-446655440000.eml`)
- **Redis Stream**: Used as the Redis hash key (`email:550e8400-e29b-41d4-a716-446655440000`)
- **Workers**: Use this ID to fetch the complete email content from storage
- **Logging**: Provides correlation ID for tracking email processing across components

The UUID4 ensures each email has a globally unique identifier with extremely low probability of collisions (~1 in 5.3 x 10^36).

### Q: If I wanted to run the SMTP server on the CLI and supply the configuration via environment variables inline, like "EMAIL_PROCESSOR=redis_stream SMTP_HOST=0.0.0.0 uv run smtp_server.py", what would that command look like?

**A:** For inline environment variables, you would use the dot-notation format for configuring the Redis Stream processor. Here's the complete command:

```bash
SMTP_HOST=0.0.0.0 \
SMTP_PORT=8025 \
LOG_LEVEL=INFO \
email.processors.0.type=redis_stream \
email.processors.0.redis_host=192.168.1.11 \
email.processors.0.redis_port=6379 \
email.processors.0.redis_db=0 \
email.processors.0.stream_name=email_queue \
email.processors.0.email_ttl=86400 \
uv run smtp_server.py
```

**Key points:**
- Use `email.processors.0.type=redis_stream` (not `EMAIL_PROCESSOR=redis_stream`)
- All processor configuration uses dot-notation format: `email.processors.0.parameter=value`
- The `0` indicates the first processor (you can add additional processors with `1`, `2`, etc.)
- Replace `192.168.1.11` with your actual Redis host IP address
- The backslashes (`\`) allow you to split the command across multiple lines for readability

**Single-line version:**
```bash
SMTP_HOST=0.0.0.0 SMTP_PORT=8025 LOG_LEVEL=INFO email.processors.0.type=redis_stream email.processors.0.redis_host=192.168.1.11 email.processors.0.redis_port=6379 email.processors.0.redis_db=0 email.processors.0.stream_name=email_queue email.processors.0.email_ttl=86400 uv run smtp_server.py
```

This configures the SMTP server to listen on `0.0.0.0:8025` and use the Redis Stream processor to connect to your Redis instance at `192.168.1.11:6379`.

## System Architecture

### Q: What is the difference between the SMTP server, processors, workers, and final processors?

**A:** These are distinct components in the email processing pipeline with specific roles:

**SMTP Server (`smtp_server.py`):**
- **Role**: Receives incoming SMTP connections and email data
- **Function**: Listens on a port (e.g., 8025), handles SMTP protocol, parses email messages
- **Processors**: Uses "email processors" to handle received emails immediately
- **Lifecycle**: Synchronous - must complete processing before responding to SMTP client
- **Examples**: Stores emails, queues for async processing, or forwards immediately

**Email Processors (SMTP Server Processors):**
- **Role**: Handle emails immediately when received by SMTP server
- **Types**: 
  - Storage-only: `file_storage`, `s3_storage`
  - Queue-only: `sqs_queue`
  - Forwarding: `ses_forwarder`, `smtpcom_api`
  - Integrated: `redis_stream`, `sqs_s3_hybrid`
- **Configuration**: `email.processors.0.type=processor_name`
- **Constraint**: Must complete quickly to avoid SMTP timeouts

**Workers (`sqs_worker.py`, `redis_worker.py`):**
- **Role**: Asynchronously process queued emails from integrated processors
- **Function**: Poll queues (SQS, Redis Streams), retrieve full email content, process through final processors
- **Lifecycle**: Runs continuously in background, processes at own pace
- **Triggers**: Only activated when using `redis_stream` or `sqs_s3_hybrid` processors

**Final Processors (Worker Processors):**
- **Role**: Perform the actual email delivery/processing after async retrieval
- **Types**: Same as email processors (`file_storage`, `ses_forwarder`, `smtpcom_api`, etc.)
- **Configuration**: `worker.processors.0.type=processor_name`
- **Advantage**: Can perform slow operations without blocking SMTP server

**Processing Flow Examples:**

**Direct Processing (No Queue):**
```
SMTP Client → SMTP Server → Email Processor (file_storage) → Done
```

**Queued Processing (Recommended):**
```
SMTP Client → SMTP Server → Email Processor (redis_stream) → Redis Queue
                                                                    ↓
Worker → Final Processor (smtpcom_api) ← Redis Queue
```

**Key Differences:**
- **SMTP Server processors**: Must be fast, handle immediate email receipt
- **Worker processors**: Can be slow, handle final delivery/processing
- **Workers**: Enable async processing to prevent SMTP timeouts
- **Integrated processors**: Bridge between immediate receipt and async processing

### Q: Can I use `smtp_server.py` by itself without a worker?

**A:** Yes, absolutely! The SMTP server can operate completely standalone using processors that don't require workers. Workers are only needed when using integrated processors that queue emails for asynchronous processing.

**Standalone Processors (No Worker Required):**
- **`file_storage`**: Saves emails directly to filesystem
- **`s3_storage`**: Stores emails directly in AWS S3
- **`ses_forwarder`**: Forwards emails immediately via AWS SES
- **`smtpcom_api`**: Sends emails immediately via SMTP.com API

**Processors That Require Workers:**
- **`redis_stream`**: Queues to Redis Streams, requires `redis_worker.py`
- **`sqs_s3_hybrid`**: Queues to SQS, requires `sqs_worker.py`
- **`sqs_queue`**: Queues to SQS, requires `sqs_worker.py`

**Example Standalone Configuration:**
```bash
# SMTP Server Settings
SMTP_HOST=0.0.0.0
SMTP_PORT=8025
LOG_LEVEL=INFO

# Direct file storage - no worker needed
email.processors.0.type=file_storage
email.processors.0.storage_dir=/var/spool/mail/processed

# Optional: Add immediate forwarding too
email.processors.1.type=smtpcom_api
email.processors.1.api_key=your-api-key
email.processors.1.channel=your-channel
```

**When to Use Standalone vs Workers:**
- **Standalone**: Simple setups, low volume, immediate processing needs
- **With Workers**: High volume, complex processing, need to prevent SMTP timeouts, want async processing benefits

The key advantage of workers is they prevent slow operations (like API calls or large file writes) from blocking the SMTP server and causing client timeouts.

### Q: When I send an email with a 60MB attachment, how does the Redis processor handle it?

**A:** The Redis Stream processor stores the complete email (including the 60MB attachment) as a binary blob in a Redis hash, which has several important implications:

**Storage Process:**
1. **SMTP Server**: Receives the complete 60MB email in memory
2. **Redis Storage**: Stores the entire email as a single Redis hash value using the email ID as the key
3. **Queue Notification**: Adds lightweight metadata to Redis Stream (without the email content)
4. **Worker Retrieval**: Worker fetches the complete 60MB email from Redis hash for processing

**Memory and Performance Considerations:**

**Redis Memory Usage:**
- The 60MB email will consume ~60MB of Redis memory until TTL expires
- Redis keeps all data in RAM, so large emails directly impact available memory
- Multiple large emails can quickly consume significant Redis memory

**Network Transfer:**
- 60MB transferred from SMTP server to Redis during storage
- 60MB transferred from Redis to worker during retrieval  
- Total: ~120MB network traffic per email

**Processing Implications:**
- **SMTP Server**: Must hold 60MB in memory during receipt and Redis storage
- **Worker**: Must load full 60MB from Redis before processing
- **Blocking**: Large transfers can temporarily block Redis operations

**Recommended Alternatives for Large Attachments:**

**For AWS Environments:**
```bash
# Use SQS+S3 Hybrid instead
email.processors.0.type=sqs_s3_hybrid
email.processors.0.queue_url=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue
email.processors.0.s3_bucket=my-email-storage-bucket
```
- S3 is designed for large objects
- Minimal memory usage in Redis/SQS
- Better cost-effectiveness for large files

**Redis Configuration Recommendations:**
```bash
# Increase Redis memory limits
maxmemory 8gb
maxmemory-policy allkeys-lru

# Shorter TTL for large emails
email.processors.0.email_ttl=3600  # 1 hour instead of 24 hours
```

**Size Limits:**
- Redis string/hash value limit: ~512MB theoretical maximum
- Practical limit: Depends on available Redis memory and concurrent emails
- Recommendation: Consider Redis unsuitable for regular emails >10MB

The Redis processor will handle 60MB emails but it's not the optimal choice for large attachments due to memory constraints and performance implications.

---

*This document is maintained as part of the Redis Stream Processor refactoring validation process.*