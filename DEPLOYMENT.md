# SMTP Server Deployment

## Architecture

The system supports two deployment architectures:

**AWS Architecture (SQS+S3)**:
```
EC2/EKS Workloads → SMTP Server → SQS Queue → Worker Processes → Final Processors
                                      ↓
                              (S3, SES, SMTP.com, etc.)
```

**Redis Architecture (Non-AWS)**:
```
Local Workloads → SMTP Server → Redis Streams → Worker Processes → Final Processors
                                      ↓
                              (File, SMTP.com, etc.)
```

## Development

### Setup with uv
```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Add Redis support (for Redis architecture)
uv add redis

# Run the SMTP server locally (SQS architecture)
uv run python smtp_server.py

# Run SQS worker locally (requires SQS_QUEUE_URL)
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue
uv run python sqs_worker.py

# Run the SMTP server locally (Redis architecture)
export email.processors.0.type=redis_hybrid
export email.processors.0.redis_host=localhost
export email.processors.0.stream_name=email_queue
uv run python smtp_server.py

# Run Redis worker locally
uv run python redis_worker.py email_queue
```

## Production Deployment (systemd)

### Automatic Installation
```bash
# Run the installation script
sudo ./install-systemd.sh
```

### Manual Installation
```bash
# Create smtp user
sudo useradd -r -s /bin/false smtp

# Create directories
sudo mkdir -p /opt/py-smtp-server

# Copy files and set ownership
sudo cp -r . /opt/py-smtp-server/
sudo chown -R smtp:smtp /opt/py-smtp-server

# Install dependencies
cd /opt/py-smtp-server
sudo -u smtp uv sync

# Install systemd services
sudo cp py-smtp-server.service /etc/systemd/system/
sudo cp py-smtp-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable py-smtp-server py-smtp-worker
```

### Service Management
```bash
# Start both services (SQS architecture)
sudo systemctl start py-smtp-server py-smtp-worker

# Start both services (Redis architecture)
sudo systemctl start py-smtp-server py-smtp-redis-worker

# Stop services
sudo systemctl stop py-smtp-server py-smtp-worker
# OR for Redis
sudo systemctl stop py-smtp-server py-smtp-redis-worker

# Check status
sudo systemctl status py-smtp-server
sudo systemctl status py-smtp-worker  # SQS
sudo systemctl status py-smtp-redis-worker  # Redis

# View logs
sudo journalctl -u py-smtp-server -f
sudo journalctl -u py-smtp-worker -f      # SQS
sudo journalctl -u py-smtp-redis-worker -f # Redis

# Restart services
sudo systemctl restart py-smtp-server py-smtp-worker
# OR for Redis
sudo systemctl restart py-smtp-server py-smtp-redis-worker
```

## Configuration

### Environment File
All configuration is managed via `/opt/py-smtp-server/.env`:

```bash
# Edit configuration
sudo nano /opt/py-smtp-server/.env

# Restart services after changes
sudo systemctl restart py-smtp-server py-smtp-worker
```

### Configuration Options

**General**:
- `SMTP_HOST`: Server bind address (default: 0.0.0.0)
- `SMTP_PORT`: Server port (default: 8025)
- `LOG_LEVEL`: Logging level (default: INFO)

**SQS Architecture**:
- `SQS_QUEUE_URL`: SQS queue URL for email processing
- `EMAIL_PROCESSORS`: JSON array of processor configurations with SQS/S3 processors

**Redis Architecture**:
- `REDIS_STREAM_NAME`: Redis Stream name for email queue (default: email_queue)
- `REDIS_HOST`: Redis server hostname (default: localhost)
- `REDIS_PORT`: Redis server port (default: 6379)
- `REDIS_DB`: Redis database number (default: 0)
- `REDIS_PASSWORD`: Redis authentication password (optional)
- `REDIS_USERNAME`: Redis authentication username (optional)
- `REDIS_SSL`: Enable SSL/TLS connection (default: false)
- `REDIS_CONSUMER_GROUP`: Consumer group name (default: workers)
- `REDIS_CONSUMER_NAME`: Consumer name (auto-generated if not provided)
- `EMAIL_PROCESSORS`: JSON array of processor configurations with Redis processors

### Redis Architecture Configuration (Recommended for Non-AWS)

**Installation Requirements**:
```bash
# Install Redis server
sudo apt update && sudo apt install redis-server

# Start and enable Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify Redis is running
redis-cli ping
```

**Environment Configuration**:
```bash
# SMTP Server uses Redis hybrid processor
EMAIL_PROCESSORS=[{"type": "redis_hybrid", "config": {"redis_host": "localhost", "redis_port": 6379, "stream_name": "email_queue", "email_ttl": 86400}}]

# Redis Worker configuration  
REDIS_STREAM_NAME=email_queue
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_CONSUMER_GROUP=workers

# Optional Redis authentication
# REDIS_PASSWORD=your_password
# REDIS_USERNAME=your_username
```

**Worker Processors (Final Processing)**:
```bash
# Configure worker processors for final email processing
worker.processors.0.type=file_storage
worker.processors.0.storage_dir=/var/spool/mail/processed

# OR send via SMTP.com
worker.processors.0.type=smtpcom_api
worker.processors.0.api_key=your_api_key
worker.processors.0.channel=your_channel
```

### SQS+S3 Hybrid Architecture Configuration (Recommended for AWS)
```bash
# SMTP Server uses hybrid processor (stores in S3 + queues metadata)
EMAIL_PROCESSORS=[{"type": "sqs_s3_hybrid", "config": {"queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/email-queue", "s3_bucket": "my-email-storage-bucket", "s3_prefix": "emails/"}}]

# SQS Worker processes from queue and retrieves full emails from S3
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue
```

### Legacy SQS Architecture Configuration
```bash
# SMTP Server uses SQS queue processor (limited by SQS message size)
EMAIL_PROCESSORS=[{"type": "sqs_queue", "config": {"queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/email-queue"}}]

# SQS Worker processes from queue (configured in worker code)
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue
```

## Backend Selection Guide

### Choose Redis Architecture When:
- Deploying on non-AWS infrastructure (on-premise, GCP, Azure, etc.)
- Need lower latency email processing
- Want simplified setup with single backend system
- Have cost constraints or want to avoid AWS service fees
- Email volume fits within Redis memory and clustering capabilities
- Prefer in-memory storage with built-in TTL

### Choose SQS+S3 Architecture When:
- Deploying on AWS infrastructure
- Need unlimited scale and AWS managed services
- Want separation of concerns (queuing vs storage)
- Require high availability with AWS SLA guarantees
- Handle large email volumes with attachments
- Prefer pay-per-use pricing model

## Infrastructure Setup

### Redis Setup (Non-AWS Deployments)
```bash
# Install Redis server
sudo apt update && sudo apt install redis-server

# Configure Redis for production
sudo nano /etc/redis/redis.conf
# Enable persistence: save 900 1
# Set memory policy: maxmemory-policy allkeys-lru  
# Configure log level: loglevel notice

# Secure Redis (optional)
# requirepass your_password
# bind 127.0.0.1

# Start and enable Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify installation
redis-cli ping
# Expected: PONG

# Test streams functionality
redis-cli XADD test_stream \* field1 value1
redis-cli XLEN test_stream
redis-cli DEL test_stream
```

### AWS Setup (SQS+S3 Architecture)
```bash
# Create SQS queue
aws sqs create-queue --queue-name email-processing-queue

# Create S3 bucket for email storage
aws s3 mb s3://my-email-storage-bucket

# Get queue URL
aws sqs get-queue-url --queue-name email-processing-queue

# Set up IAM permissions for EC2 instances to access SQS and S3
```

## Testing

### Redis Architecture Testing
```bash
# Send test email using telnet
telnet localhost 8025
# ... SMTP commands ...

# Check Redis queue for messages
redis-cli XLEN email_queue

# Check email storage in Redis
redis-cli KEYS "email:*"
redis-cli HGETALL "email:some-uuid"

# Monitor Redis worker processing
sudo journalctl -u py-smtp-redis-worker -f

# Test Redis connectivity
redis-cli ping

# Monitor Redis memory usage
redis-cli INFO memory
```

### SQS Architecture Testing
```bash
# Send test email using telnet
telnet localhost 8025

# Check SQS queue for messages
aws sqs get-queue-attributes --queue-url YOUR_QUEUE_URL --attribute-names ApproximateNumberOfMessages

# Monitor worker processing
sudo journalctl -u py-smtp-worker -f
```

## Scaling

### Redis Architecture Scaling

**Horizontal Scaling**:
```bash
# Deploy multiple SMTP server instances
# All write to same Redis Stream
# Use load balancer for SMTP connections

# Deploy multiple Redis worker instances
# Each worker uses different consumer name in same consumer group
# Redis Streams distribute messages across consumers
```

**Redis Scaling Considerations**:
- Single Redis instance: Up to ~100GB memory, high throughput
- Redis Cluster: Distribute across multiple nodes for larger scale
- Redis Sentinel: High availability with automatic failover
- Monitor memory usage and configure appropriate `maxmemory` policy

**Worker Scaling**:
```bash
# Scale based on stream length
redis-cli XLEN email_queue

# Add more workers with unique consumer names
REDIS_CONSUMER_NAME=worker-1 python redis_worker.py email_queue
REDIS_CONSUMER_NAME=worker-2 python redis_worker.py email_queue
REDIS_CONSUMER_NAME=worker-3 python redis_worker.py email_queue
```

### SQS Architecture Scaling

**SMTP Servers**:
- Deploy multiple SMTP server instances
- Use load balancer to distribute connections
- All instances write to same SQS queue

**Workers**:
- Deploy multiple worker instances
- Each worker polls same SQS queue
- Auto-scale based on queue depth

**SQS Configuration**:
- Configure dead letter queue for failed messages
- Set appropriate visibility timeout
- Enable long polling for efficiency
