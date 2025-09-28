# Python SMTP Server

A production-ready, standalone Python SMTP server using aiosmtpd with a decoupled SQS-based architecture for high availability and horizontal scaling in AWS VPC environments.

## Architecture

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

## Key Features

- **Decoupled Architecture**: SMTP reception separate from email processing via queues
- **Multiple Queue Backends**: SQS+S3 for AWS, Redis+Streams for on-premise/non-AWS
- **Horizontal Scaling**: Multiple SMTP servers and workers with shared queue
- **Modular Processors**: Pluggable email routing (S3, SES, SMTP.com, File Storage)
- **Production Ready**: Systemd integration, logging, error handling, signal management
- **AWS Native**: Designed for VPC deployment with SQS, S3, SES integration
- **Redis Alternative**: Single backend system for simplified on-premise deployments
- **High Availability**: Queue-based buffering handles traffic spikes and failures

## Quick Start

### Development

```bash
# Install dependencies
uv sync

# Run SMTP server locally
uv run python smtp_server.py

# Run SQS worker (requires SQS_QUEUE_URL)
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue
uv run python sqs_worker.py
```

### Redis Alternative (Non-AWS)

```bash
# Install Redis
sudo apt install redis-server

# Install dependencies with Redis support
uv sync
uv add redis

# Run SMTP server with Redis hybrid processor
export email.processors.0.type=redis_hybrid
export email.processors.0.redis_host=localhost
export email.processors.0.stream_name=email_queue
export email.processors.0.email_ttl=86400
uv run python smtp_server.py

# Run Redis worker
export worker.redis.stream_name=email_queue
uv run python redis_worker.py
```

### Production Deployment

```bash
# Install as systemd services
sudo ./install-systemd.sh

# Configure environment
sudo nano /opt/py-smtp-server/.env

# Start services
sudo systemctl start py-smtp-server py-smtp-worker
```

## Configuration

All configuration is managed via environment variables in `/opt/py-smtp-server/.env`:

```bash
# SMTP Server
SMTP_HOST=0.0.0.0
SMTP_PORT=8025
LOG_LEVEL=INFO

# SQS Integration (for worker)
worker.sqs.queue_url=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue

# Processor Configuration (dot-notation)
# SQS+S3 Hybrid (AWS)
email.processors.0.type=sqs_s3_hybrid
email.processors.0.queue_url=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue
email.processors.0.s3_bucket=my-email-storage-bucket

# Redis Alternative (non-AWS)
email.processors.0.type=redis_hybrid
email.processors.0.redis_host=localhost
email.processors.0.stream_name=email_queue
email.processors.0.email_ttl=86400

# Redis Worker Configuration
worker.redis.stream_name=email_queue
worker.redis.host=localhost
worker.redis.port=6379
worker.redis.db=0
worker.redis.consumer_group=workers

# Worker Processors (for final processing)
worker.processors.0.type=file_storage
worker.processors.0.storage_dir=/var/spool/mail/processed
```

## Available Processors

- **SQSS3HybridProcessor**: Store emails in S3 + queue metadata in SQS (recommended for production)
- **RedisHybridProcessor**: Store emails in Redis + queue metadata in Redis Streams (recommended for non-AWS)
- **SQSQueueProcessor**: Queue emails to SQS for async processing
- **FileStorageProcessor**: Save emails as files on disk
- **S3StorageProcessor**: Store emails in AWS S3 buckets
- **SESForwarderProcessor**: Forward emails via AWS SES
- **SMTPComAPIProcessor**: Send emails via SMTP.com REST API with attachment support

## Backend Comparison

| Feature | SQS+S3 (AWS) | Redis Hybrid |
|---------|--------------|--------------|
| **Infrastructure** | AWS SQS + S3 | Single Redis instance |
| **Setup Complexity** | AWS configuration | Simple installation |
| **Latency** | Higher (network + S3) | Lower (in-memory) |
| **Scalability** | Unlimited (AWS managed) | Redis cluster limits |
| **Cost** | Pay per use | Self-hosted |
| **Reliability** | AWS SLA guarantees | Redis persistence |
| **TTL** | S3 lifecycle policies | Built-in expiration |
| **Dependencies** | boto3, AWS credentials | redis-py |
| **Best For** | AWS-native deployments | On-premise, non-AWS |

### Choose SQS+S3 when:
- Running on AWS infrastructure
- Need unlimited scale
- Want managed services
- Require high availability guarantees

### Choose Redis when:
- On-premise or non-AWS deployments
- Need lower latency
- Want simple setup
- Have cost constraints

## Documentation

### Core Documentation
- **[Architecture Guide](docs/ARCHITECTURE.md)** - Detailed system architecture and design decisions
- **[API Documentation](docs/API.md)** - Processor interface and configuration reference
- **[Operations Guide](docs/OPERATIONS.md)** - Service management, monitoring, and troubleshooting
- **[Deployment Guide](DEPLOYMENT.md)** - Installation and deployment instructions
- **[Rule Engine Guide](docs/RULE_ENGINE.md)** - Complete rule-based routing documentation
- **[Rule Engine Roadmap](docs/RULE_ENGINE_ROADMAP.md)** - Planned features and enhancements

### Configuration Examples
- **[Environment File Example](.env.example)** - Complete configuration template
- **[Routing Rules Schema](schemas/routing_rules.json)** - JSON schema for email routing rules
- **[Parameter Store Structure](examples/parameter_store_structure.md)** - AWS Parameter Store integration

### Service Files
- **[SMTP Server Service](py-smtp-server.service)** - Systemd service for SMTP server
- **[SQS Worker Service](py-smtp-worker.service)** - Systemd service for SQS worker
- **[Installation Script](install-systemd.sh)** - Automated installation script

## Testing

```bash
# Send test email via telnet
telnet localhost 8025
HELO test
MAIL FROM: test@example.com
RCPT TO: recipient@example.com
DATA
Subject: Test Email

This is a test email.
.
QUIT

# Check SQS queue for messages
aws sqs get-queue-attributes --queue-url $SQS_QUEUE_URL --attribute-names ApproximateNumberOfMessages

# Check Redis queue for messages (Redis alternative)
redis-cli XLEN email_queue

# Run all automated tests
./run_tests.sh

# Run selective tests (useful when some components are incomplete)
./run_tests.sh redis           # Run only Redis tests
./run_tests.sh local syntax    # Run local and syntax tests
./run_tests.sh config          # Run only configuration tests

# Available test groups: local, redis, syntax, config, all
# - local: Multi-processor configuration and instantiation tests
# - redis: Redis-specific functionality and integration tests  
# - syntax: Python syntax validation and import checks
# - config: Configuration loading and processor creation tests
# - all: All test groups (default)

# Test worker imports and functionality
./test-workers.sh

# Run automated Redis test
./test-redis.sh

# Monitor processing
sudo journalctl -u py-smtp-worker -f
# OR for Redis worker
sudo journalctl -u py-smtp-redis-worker -f
```

## Monitoring

### Service Status
```bash
# Check service status (SQS version)
sudo systemctl status py-smtp-server py-smtp-worker

# Check service status (Redis version)
sudo systemctl status py-smtp-server py-smtp-redis-worker

# View logs
sudo journalctl -u py-smtp-server -u py-smtp-worker -f
# OR for Redis
sudo journalctl -u py-smtp-server -u py-smtp-redis-worker -f
```

### Health Checks
- **SMTP Server**: TCP connection test on port 8025
- **SQS Worker**: Message processing rate and error logs
- **Redis Worker**: Stream processing rate and Redis connectivity
- **Queue Health**: SQS queue depth / Redis stream length and message age

## Scaling

### Horizontal Scaling
- **SMTP Servers**: Deploy multiple instances behind load balancer
- **Workers**: Deploy multiple worker instances polling same queue
- **Auto Scaling**: Scale based on queue depth and processing metrics

### Performance Characteristics
- **SMTP Server**: ~1000 concurrent connections per instance
- **Worker**: ~100 messages/second per instance
- **Queue**: Unlimited buffering capacity via SQS

## Security

### Network Security
- Deploy in private subnets with VPC endpoints
- Security groups restrict access to port 8025
- No internet gateway required for AWS service access

### Process Security
- Runs as dedicated `smtp` user with no shell access
- Systemd security restrictions (NoNewPrivileges, PrivateTmp, etc.)
- Environment-based configuration with secure parameter storage

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
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::my-email-storage-bucket/*"
    }
  ]
}
```

## Development

### Requirements
- Python 3.12+
- uv package manager
- AWS CLI (for SQS integration)
- systemd (for production deployment)

### Dependencies
- **aiosmtpd**: Async SMTP server implementation
- **boto3**: AWS SDK for SQS integration
- **requests**: HTTP client for API processors

### Creating Custom Processors

```python
from processors.base import EmailProcessor

class CustomProcessor(EmailProcessor):
    async def process(self, envelope, message) -> bool:
        # Your processing logic here
        return True
    
    def get_name(self) -> str:
        return "CustomProcessor"
```

## Roadmap

### Planned Features
- [ ] Rule-based email routing with AWS Parameter Store integration
- [ ] Prometheus metrics with dimensional labels
- [ ] Hot-reloadable configuration with forking process model
- [ ] Authentication mechanisms (PLAIN, LOGIN)
- [ ] TLS/SSL support for secure connections
- [ ] Rate limiting per client/IP
- [ ] VPC endpoint support for private subnet workloads
- [ ] Connection pooling and load balancing optimizations

### Future Enhancements
- Multi-AZ deployment with automatic failover
- Container deployment for ECS/EKS
- Circuit breaker pattern for downstream services
- Email deduplication and batch processing
- Advanced monitoring and alerting integration

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with appropriate tests
4. Update documentation as needed
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or contributions:
- Create an issue in the GitHub repository
- Review the [Operations Guide](docs/OPERATIONS.md) for troubleshooting
- Check the [API Documentation](docs/API.md) for configuration help