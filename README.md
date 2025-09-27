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

- **Decoupled Architecture**: SMTP reception separate from email processing via SQS
- **Horizontal Scaling**: Multiple SMTP servers and workers with shared queue
- **Modular Processors**: Pluggable email routing (S3, SES, SMTP.com, File Storage)
- **Production Ready**: Systemd integration, logging, error handling, signal management
- **AWS Native**: Designed for VPC deployment with SQS, S3, SES integration
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

# SQS Integration
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue

# Processor Configuration (JSON)
EMAIL_PROCESSORS=[{"type": "sqs_s3_hybrid", "config": {"queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/email-queue", "s3_bucket": "my-email-storage-bucket"}}]
```

## Available Processors

- **SQSS3HybridProcessor**: Store emails in S3 + queue metadata in SQS (recommended for production)
- **SQSQueueProcessor**: Queue emails to SQS for async processing
- **FileStorageProcessor**: Save emails as files on disk
- **S3StorageProcessor**: Store emails in AWS S3 buckets
- **SESForwarderProcessor**: Forward emails via AWS SES
- **SMTPComAPIProcessor**: Send emails via SMTP.com REST API with attachment support

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

# Monitor processing
sudo journalctl -u py-smtp-worker -f
```

## Monitoring

### Service Status
```bash
# Check service status
sudo systemctl status py-smtp-server py-smtp-worker

# View logs
sudo journalctl -u py-smtp-server -u py-smtp-worker -f
```

### Health Checks
- **SMTP Server**: TCP connection test on port 8025
- **SQS Worker**: Message processing rate and error logs
- **Queue Health**: SQS queue depth and message age

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