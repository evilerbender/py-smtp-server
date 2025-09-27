# SMTP Server Deployment

## Architecture

The system uses a decoupled SQS-based architecture:

```
EC2/EKS Workloads → SMTP Server → SQS Queue → Worker Processes → Final Processors
                                      ↓
                              (S3, SES, SMTP.com, etc.)
```

## Development

### Setup with uv
```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run the SMTP server locally
uv run python smtp_server.py

# Run SQS worker locally (requires SQS_QUEUE_URL)
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue
uv run python sqs_worker.py
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
# Start both services
sudo systemctl start py-smtp-server py-smtp-worker

# Stop services
sudo systemctl stop py-smtp-server py-smtp-worker

# Check status
sudo systemctl status py-smtp-server
sudo systemctl status py-smtp-worker

# View logs
sudo journalctl -u py-smtp-server -f
sudo journalctl -u py-smtp-worker -f

# Restart services
sudo systemctl restart py-smtp-server py-smtp-worker
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
- `SMTP_HOST`: Server bind address (default: 0.0.0.0)
- `SMTP_PORT`: Server port (default: 8025)
- `LOG_LEVEL`: Logging level (default: INFO)
- `SQS_QUEUE_URL`: SQS queue URL for email processing
- `EMAIL_PROCESSORS`: JSON array of processor configurations

### SQS+S3 Hybrid Architecture Configuration (Recommended)
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

### AWS Setup
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
```bash
# Send test email using telnet
telnet localhost 8025

# Check SQS queue for messages
aws sqs get-queue-attributes --queue-url YOUR_QUEUE_URL --attribute-names ApproximateNumberOfMessages

# Monitor worker processing
sudo journalctl -u py-smtp-worker -f
```

## Scaling

### SMTP Servers
- Deploy multiple SMTP server instances
- Use load balancer to distribute connections
- All instances write to same SQS queue

### Workers
- Deploy multiple worker instances
- Each worker polls same SQS queue
- Auto-scale based on queue depth

### SQS Configuration
- Configure dead letter queue for failed messages
- Set appropriate visibility timeout
- Enable long polling for efficiency
