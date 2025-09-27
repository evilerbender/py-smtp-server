# Operations Guide

## Service Management

### Starting Services

```bash
# Start both SMTP server and worker
sudo systemctl start py-smtp-server py-smtp-worker

# Start individually
sudo systemctl start py-smtp-server
sudo systemctl start py-smtp-worker

# Enable auto-start on boot
sudo systemctl enable py-smtp-server py-smtp-worker
```

### Stopping Services

```bash
# Stop both services
sudo systemctl stop py-smtp-server py-smtp-worker

# Stop individually
sudo systemctl stop py-smtp-server
sudo systemctl stop py-smtp-worker

# Disable auto-start
sudo systemctl disable py-smtp-server py-smtp-worker
```

### Service Status

```bash
# Check status of both services
sudo systemctl status py-smtp-server py-smtp-worker

# Check individual service status
sudo systemctl status py-smtp-server
sudo systemctl status py-smtp-worker

# Check if services are enabled
sudo systemctl is-enabled py-smtp-server py-smtp-worker
```

## Monitoring and Logging

### Viewing Logs

```bash
# Follow logs for both services
sudo journalctl -u py-smtp-server -u py-smtp-worker -f

# Follow SMTP server logs only
sudo journalctl -u py-smtp-server -f

# Follow worker logs only
sudo journalctl -u py-smtp-worker -f

# View recent logs (last 100 lines)
sudo journalctl -u py-smtp-server -n 100

# View logs from specific time
sudo journalctl -u py-smtp-server --since "2024-01-15 10:00:00"
sudo journalctl -u py-smtp-server --since "1 hour ago"
```

### Log Analysis

**Key Log Messages to Monitor**:

**SMTP Server**:
- `SMTP server started on 0.0.0.0:8025` - Successful startup
- `Received email from sender@example.com to ['recipient@example.com']` - Email received
- `Email processed successfully by SQSQueue` - Successful queuing
- `Email processing failed in SQSQueue` - Queue failure
- `Error processing email: <error>` - Processing error

**SQS Worker**:
- `SQS worker started, polling queue: <url>` - Successful startup
- `Successfully processed email <id>` - Successful processing
- `Failed to process email <id>` - Processing failure
- `Error polling SQS: <error>` - SQS connection issues
- `Error in processor <name>: <error>` - Processor-specific errors

### Health Checks

**SMTP Server Health**:
```bash
# Test SMTP connection
telnet localhost 8025

# Expected response:
# 220 <hostname> Python SMTP <version>

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
```

**SQS Worker Health**:
```bash
# Check if worker is processing messages
sudo journalctl -u py-smtp-worker --since "5 minutes ago" | grep "Successfully processed"

# Check for worker errors
sudo journalctl -u py-smtp-worker --since "1 hour ago" | grep ERROR

# Monitor SQS queue depth
aws sqs get-queue-attributes \
  --queue-url $SQS_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages
```

## Configuration Management

### Updating Configuration

```bash
# Edit configuration file
sudo nano /opt/py-smtp-server/.env

# Restart services to apply changes
sudo systemctl restart py-smtp-server py-smtp-worker

# Verify configuration is loaded
sudo journalctl -u py-smtp-server -n 20 | grep "Configured processors"
sudo journalctl -u py-smtp-worker -n 20 | grep "Configured processors"
```

### Configuration Validation

**Check Environment File**:
```bash
# Verify environment file exists and is readable
sudo -u smtp cat /opt/py-smtp-server/.env

# Check for required variables
grep -E "^(SMTP_HOST|SMTP_PORT|SQS_QUEUE_URL|EMAIL_PROCESSORS)" /opt/py-smtp-server/.env
```

**Validate JSON Configuration**:
```bash
# Extract and validate EMAIL_PROCESSORS JSON
grep "^EMAIL_PROCESSORS=" /opt/py-smtp-server/.env | cut -d'=' -f2- | python3 -m json.tool
```

### Common Configuration Issues

**Invalid JSON in EMAIL_PROCESSORS**:
```bash
# Symptoms: Service fails to start with JSON decode error
# Fix: Validate JSON syntax
echo '$EMAIL_PROCESSORS_VALUE' | python3 -m json.tool

# Common issues:
# - Missing quotes around strings
# - Trailing commas
# - Unescaped quotes in values
```

**Missing SQS Queue URL**:
```bash
# Symptoms: Worker exits with "SQS_QUEUE_URL environment variable required"
# Fix: Add SQS_QUEUE_URL to .env file
echo "SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue" >> /opt/py-smtp-server/.env
```

## Troubleshooting

### Common Issues

**SMTP Server Won't Start**:

1. **Port Already in Use**:
   ```bash
   # Check what's using port 8025
   sudo netstat -tlnp | grep :8025
   sudo lsof -i :8025
   
   # Change port in configuration
   sudo nano /opt/py-smtp-server/.env
   # Set SMTP_PORT=8026
   ```

2. **Permission Denied**:
   ```bash
   # Check service file permissions
   ls -la /etc/systemd/system/py-smtp-server.service
   
   # Check user exists
   id smtp
   
   # Check directory permissions
   ls -la /opt/py-smtp-server/
   ```

3. **Missing Dependencies**:
   ```bash
   # Check if virtual environment exists
   ls -la /opt/py-smtp-server/.venv/
   
   # Reinstall dependencies
   cd /opt/py-smtp-server
   sudo -u smtp uv sync
   ```

**SQS Worker Issues**:

1. **AWS Credentials**:
   ```bash
   # Check if EC2 instance has IAM role
   curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/
   
   # Test SQS access
   aws sqs get-queue-attributes --queue-url $SQS_QUEUE_URL --attribute-names QueueArn
   ```

2. **Queue Not Found**:
   ```bash
   # Verify queue exists
   aws sqs list-queues | grep email-processing-queue
   
   # Check queue URL format
   echo $SQS_QUEUE_URL
   ```

3. **Message Processing Failures**:
   ```bash
   # Check dead letter queue
   aws sqs get-queue-attributes \
     --queue-url $DLQ_URL \
     --attribute-names ApproximateNumberOfMessages
   
   # Examine failed messages
   aws sqs receive-message --queue-url $DLQ_URL
   ```

### Performance Issues

**High CPU Usage**:
```bash
# Check process CPU usage
top -p $(pgrep -f "smtp_server.py|sqs_worker.py")

# Check connection count
ss -tlnp | grep :8025

# Monitor email processing rate
sudo journalctl -u py-smtp-server --since "1 hour ago" | grep "Email processed" | wc -l
```

**High Memory Usage**:
```bash
# Check memory usage
ps aux | grep -E "smtp_server.py|sqs_worker.py"

# Check for memory leaks
sudo journalctl -u py-smtp-server --since "1 hour ago" | grep -i memory
```

**Slow Processing**:
```bash
# Check SQS queue depth
aws sqs get-queue-attributes \
  --queue-url $SQS_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages,ApproximateAgeOfOldestMessage

# Monitor processing times
sudo journalctl -u py-smtp-worker -f | grep "processed email"
```

## Maintenance

### Log Rotation

Logs are managed by systemd/journald. Configure retention:

```bash
# Edit journald configuration
sudo nano /etc/systemd/journald.conf

# Set retention policy
SystemMaxUse=1G
MaxRetentionSec=7day

# Restart journald
sudo systemctl restart systemd-journald
```

### Backup and Recovery

**Configuration Backup**:
```bash
# Backup configuration
sudo cp /opt/py-smtp-server/.env /opt/py-smtp-server/.env.backup.$(date +%Y%m%d)

# Backup entire installation
sudo tar -czf /tmp/py-smtp-server-backup-$(date +%Y%m%d).tar.gz /opt/py-smtp-server/
```

**Recovery**:
```bash
# Restore configuration
sudo cp /opt/py-smtp-server/.env.backup.20240115 /opt/py-smtp-server/.env
sudo systemctl restart py-smtp-server py-smtp-worker

# Full restoration
sudo tar -xzf /tmp/py-smtp-server-backup-20240115.tar.gz -C /
sudo systemctl daemon-reload
sudo systemctl restart py-smtp-server py-smtp-worker
```

### Updates

**Update Application**:
```bash
# Stop services
sudo systemctl stop py-smtp-server py-smtp-worker

# Backup current installation
sudo cp -r /opt/py-smtp-server /opt/py-smtp-server.backup.$(date +%Y%m%d)

# Update code (example with git)
cd /opt/py-smtp-server
sudo -u smtp git pull

# Update dependencies
sudo -u smtp uv sync

# Restart services
sudo systemctl start py-smtp-server py-smtp-worker

# Verify services are running
sudo systemctl status py-smtp-server py-smtp-worker
```

**Update System Dependencies**:
```bash
# Update system packages
sudo apt update && sudo apt upgrade

# Update Python if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Reinstall Python dependencies
cd /opt/py-smtp-server
sudo -u smtp uv sync --upgrade
```

## Scaling

### Horizontal Scaling

**Multiple SMTP Servers**:
```bash
# Deploy on multiple instances
# Each instance writes to the same SQS queue
# Use load balancer to distribute connections

# Example with Network Load Balancer:
# Target Group: Port 8025, TCP health check
# Health Check: TCP connection to port 8025
```

**Multiple Workers**:
```bash
# Deploy worker on multiple instances
# All workers poll the same SQS queue
# SQS handles message distribution automatically

# Scale based on queue depth:
aws cloudwatch put-metric-alarm \
  --alarm-name "SQS-Queue-Depth-High" \
  --alarm-description "Scale up when queue depth > 100" \
  --metric-name ApproximateNumberOfMessages \
  --namespace AWS/SQS \
  --statistic Average \
  --period 300 \
  --threshold 100 \
  --comparison-operator GreaterThanThreshold
```

### Vertical Scaling

**Increase Instance Size**:
- Monitor CPU and memory usage
- Scale up instance type if consistently high utilization
- Consider memory-optimized instances for high-throughput scenarios

**Optimize Configuration**:
```bash
# Increase worker batch size (modify sqs_worker.py)
MaxNumberOfMessages=10  # Default, can increase to 10 max

# Adjust polling intervals
WaitTimeSeconds=20      # Long polling, optimal for most cases

# Tune systemd service limits
sudo systemctl edit py-smtp-server
[Service]
LimitNOFILE=65536
```

## Security

### Access Control

**File Permissions**:
```bash
# Verify correct ownership
sudo chown -R smtp:smtp /opt/py-smtp-server/
sudo chmod 600 /opt/py-smtp-server/.env

# Check service file permissions
sudo chmod 644 /etc/systemd/system/py-smtp-*.service
```

**Network Security**:
```bash
# Restrict SMTP access to VPC only
# Security Group: Allow port 8025 from VPC CIDR only

# Monitor connections
sudo netstat -an | grep :8025
sudo ss -tlnp | grep :8025
```

### Monitoring for Security Issues

**Failed Authentication Attempts**:
```bash
# Monitor for suspicious connection patterns
sudo journalctl -u py-smtp-server | grep -E "(rejected|failed|error)" | tail -20
```

**Resource Exhaustion**:
```bash
# Monitor for DoS attempts
sudo journalctl -u py-smtp-server | grep -E "(too many|limit|throttle)" | tail -20
```

## Alerting

### CloudWatch Integration

**Custom Metrics**:
```bash
# Send custom metrics to CloudWatch
aws cloudwatch put-metric-data \
  --namespace "SMTP/Server" \
  --metric-data MetricName=EmailsProcessed,Value=1,Unit=Count
```

**Log-based Alarms**:
```bash
# Create alarm for error rate
aws logs create-log-group --log-group-name /systemd/py-smtp-server

# Set up metric filter for errors
aws logs put-metric-filter \
  --log-group-name /systemd/py-smtp-server \
  --filter-name ErrorCount \
  --filter-pattern "ERROR" \
  --metric-transformations \
    metricName=ErrorCount,metricNamespace=SMTP/Server,metricValue=1
```

### Email Alerts

**Service Failures**:
```bash
# Configure systemd to send email on failure
sudo systemctl edit py-smtp-server
[Unit]
OnFailure=status-email@%n.service

# Create email notification service
sudo nano /etc/systemd/system/status-email@.service
```
