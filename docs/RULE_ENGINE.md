# Rule-Based Email Routing Engine

## Overview

The Rule Engine provides conditional email routing based on configurable rules stored in AWS Parameter Store. Instead of broadcasting emails to all processors, the engine evaluates rules against incoming emails and routes them only to matching processors.

## Architecture

```
Email → Rule Engine → Rule Matching → Selected Processors → Final Delivery
```

### Benefits
- **Conditional Processing**: Route emails based on content, headers, sender/recipient
- **Cost Optimization**: Only run necessary processors
- **Dynamic Configuration**: Update rules without code changes
- **Environment Separation**: Different routing for prod/dev/test
- **Centralized Management**: Rules stored in AWS Parameter Store

## Configuration

### Environment Variables

```bash
# Enable rule-based routing
RULE_ENGINE_PARAMETER=/email-routing/rules
AWS_REGION=us-east-1

# SQS worker will use rule engine instead of static processors
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/email-queue
```

### AWS Parameter Store Setup

1. **Create Parameter**:
   ```bash
   aws ssm put-parameter \
     --name "/email-routing/rules" \
     --type "String" \
     --value "$(cat rules.json)"
   ```

2. **For Encrypted Rules** (recommended):
   ```bash
   aws ssm put-parameter \
     --name "/email-routing/rules" \
     --type "SecureString" \
     --value "$(cat rules.json)" \
     --key-id "alias/parameter-store-key"
   ```

## Rule Configuration Format

### Basic Structure

```json
{
  "rules": [
    {
      "name": "rule_name",
      "conditions": {
        "matching_criteria": "values"
      },
      "processors": ["processor_name1", "processor_name2"]
    }
  ],
  "processors": {
    "processor_name1": {
      "type": "processor_type",
      "config_key": "config_value"
    }
  }
}
```

### Rule Processing Logic

1. **Sequential Evaluation**: Rules processed in array order
2. **First Match Wins**: First matching rule determines processors
3. **Default Rule**: Empty conditions `{}` match everything
4. **No Match**: Email not processed if no rules match

## Matching Conditions

### Basic Conditions

#### Email Addresses
```json
{
  "from_email": "user@company.com",
  "to_email": "support@company.com"
}
```

#### Domain Matching
```json
{
  "from_domain": "company.com",
  "to_domain": ["client1.com", "client2.com"]
}
```

#### Subject Matching
```json
{
  "subject_contains": ["URGENT", "CRITICAL"]
}
```

#### Header Matching
```json
{
  "header_exists": ["X-Priority", "X-Marketing-Campaign"],
  "header_value": {
    "X-Priority": "1",
    "X-Marketing-Campaign": "summer2024"
  }
}
```

### Advanced Matching (Planned)

#### Content-Based
```json
{
  "body_contains": ["password reset", "invoice"],
  "attachment_count": {"min": 1, "max": 5},
  "attachment_types": [".pdf", ".docx"],
  "message_size": {"max_mb": 10}
}
```

#### Time-Based
```json
{
  "time_of_day": "09:00-17:00",
  "day_of_week": ["monday", "tuesday", "wednesday", "thursday", "friday"],
  "date_range": {
    "start": "2024-01-01",
    "end": "2024-12-31"
  }
}
```

#### Pattern Matching
```json
{
  "regex_patterns": {
    "subject": "^\\[TICKET-\\d+\\]",
    "from_email": ".*@(company|subsidiary)\\.com$"
  },
  "wildcard_domains": ["*.company.com", "*.partner.org"],
  "negation": {
    "NOT": {
      "from_domain": "spam.com",
      "subject_contains": ["unsubscribe"]
    }
  }
}
```

## Processor Configuration

### Supported Processor Types

#### SMTP.com API
```json
{
  "type": "smtpcom_api",
  "api_key": "your-api-key",
  "channel": "production"
}
```

#### S3 Storage
```json
{
  "type": "s3_storage",
  "bucket_name": "email-archive",
  "key_prefix": "emails/"
}
```

#### SES Forwarder
```json
{
  "type": "ses_forwarder",
  "region": "us-east-1",
  "from_email": "noreply@company.com"
}
```

#### File Storage
```json
{
  "type": "file_storage",
  "storage_dir": "/var/spool/mail"
}
```

## Example Configurations

### Production Email Routing

```json
{
  "rules": [
    {
      "name": "urgent_emails",
      "conditions": {
        "subject_contains": ["URGENT", "CRITICAL", "EMERGENCY"],
        "from_domain": ["company.com", "partner.com"]
      },
      "processors": ["smtpcom_priority", "slack_notification", "s3_archive"]
    },
    {
      "name": "customer_support",
      "conditions": {
        "to_email": ["support@company.com", "help@company.com"]
      },
      "processors": ["smtpcom_support", "zendesk_integration", "s3_archive"]
    },
    {
      "name": "marketing_emails",
      "conditions": {
        "header_exists": "X-Marketing-Campaign",
        "from_domain": "company.com"
      },
      "processors": ["smtpcom_marketing", "analytics_tracker"]
    },
    {
      "name": "internal_emails",
      "conditions": {
        "from_domain": "company.com",
        "to_domain": ["client1.com", "client2.com"]
      },
      "processors": ["smtpcom_production"]
    },
    {
      "name": "test_emails",
      "conditions": {
        "from_domain": "test.company.com"
      },
      "processors": ["smtpcom_development", "s3_archive"]
    },
    {
      "name": "default_archive",
      "conditions": {},
      "processors": ["s3_archive"]
    }
  ],
  "processors": {
    "smtpcom_priority": {
      "type": "smtpcom_api",
      "api_key": "priority-key-here",
      "channel": "priority"
    },
    "smtpcom_support": {
      "type": "smtpcom_api", 
      "api_key": "support-key-here",
      "channel": "support"
    },
    "smtpcom_marketing": {
      "type": "smtpcom_api",
      "api_key": "marketing-key-here", 
      "channel": "marketing"
    },
    "smtpcom_production": {
      "type": "smtpcom_api",
      "api_key": "prod-key-here",
      "channel": "production"
    },
    "smtpcom_development": {
      "type": "smtpcom_api",
      "api_key": "dev-key-here",
      "channel": "development"
    },
    "s3_archive": {
      "type": "s3_storage",
      "bucket_name": "company-email-archive",
      "key_prefix": "emails/"
    },
    "slack_notification": {
      "type": "webhook",
      "url": "https://hooks.slack.com/services/...",
      "format": "slack"
    },
    "zendesk_integration": {
      "type": "webhook",
      "url": "https://company.zendesk.com/api/v2/tickets",
      "format": "zendesk"
    },
    "analytics_tracker": {
      "type": "webhook",
      "url": "https://analytics.company.com/email-events",
      "format": "json"
    }
  }
}
```

### Development/Testing Configuration

```json
{
  "rules": [
    {
      "name": "all_emails_to_dev",
      "conditions": {},
      "processors": ["dev_channel", "local_storage"]
    }
  ],
  "processors": {
    "dev_channel": {
      "type": "smtpcom_api",
      "api_key": "dev-key",
      "channel": "development"
    },
    "local_storage": {
      "type": "file_storage",
      "storage_dir": "/tmp/dev-emails"
    }
  }
}
```

## IAM Permissions

### Required Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter"
      ],
      "Resource": "arn:aws:ssm:*:*:parameter/email-routing/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:*:*:key/*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "ssm.*.amazonaws.com"
        }
      }
    }
  ]
}
```

### Least Privilege Example

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:us-east-1:123456789012:parameter/email-routing/rules"
    }
  ]
}
```

## Monitoring and Debugging

### Logging

The rule engine provides detailed logging:

```
INFO: Loaded 6 rules and 8 processors
INFO: Email matched rule 'urgent_emails', using processors: ['smtpcom_priority', 's3_archive']
WARNING: No rules matched email, no processors selected
ERROR: Processor 'smtpcom_priority' not found in configuration
```

### Rule Testing

Test rules without affecting production:

```bash
# Test rule matching locally
python -c "
from rule_engine import RuleEngine
from email.message import EmailMessage

# Create test email
msg = EmailMessage()
msg['From'] = 'test@company.com'
msg['Subject'] = 'URGENT: System Down'

# Test matching (mock mode)
engine = RuleEngine('/email-routing/test-rules')
# ... test logic
"
```

## Troubleshooting

### Common Issues

#### No Rules Matched
```
WARNING: No rules matched email, no processors selected
```
**Solution**: Add a default rule with empty conditions `{}`

#### Parameter Not Found
```
ERROR: Parameter '/email-routing/rules' not found in Parameter Store
```
**Solution**: Create the parameter or check the parameter name

#### Invalid JSON
```
ERROR: Invalid JSON in parameter '/email-routing/rules': Expecting ',' delimiter
```
**Solution**: Validate JSON syntax before storing in Parameter Store

#### Processor Not Found
```
ERROR: Processor 'smtpcom_prod' not found in configuration
```
**Solution**: Ensure processor is defined in the `processors` section

### Validation

Validate rule configuration before deployment:

```bash
# Validate JSON syntax
cat rules.json | jq '.'

# Check required fields
cat rules.json | jq '.rules[] | select(.name == null or .conditions == null or .processors == null)'

# Verify processor references
cat rules.json | jq -r '.rules[].processors[]' | sort -u > used_processors.txt
cat rules.json | jq -r '.processors | keys[]' | sort -u > defined_processors.txt
diff used_processors.txt defined_processors.txt
```

## Performance Considerations

### Rule Optimization

1. **Order Rules by Frequency**: Place most common matches first
2. **Specific Before General**: Specific conditions before broad ones
3. **Limit Rule Count**: Keep under 50 rules for optimal performance
4. **Cache Parameter Store**: Rules are cached until worker restart

### Memory Usage

- Rules loaded once at startup
- Processor instances created per email (not cached)
- Memory usage scales with rule complexity, not email volume

## Security Considerations

### Parameter Store Security

1. **Use SecureString**: Encrypt sensitive configuration
2. **Least Privilege IAM**: Restrict parameter access
3. **Audit Access**: Monitor parameter access logs
4. **Rotate Keys**: Regular rotation of API keys in rules

### Rule Validation

1. **Input Sanitization**: Email headers are untrusted input
2. **Regex Safety**: Avoid complex regex patterns (DoS risk)
3. **Processor Validation**: Validate processor configurations
4. **Access Control**: Restrict who can modify rules

## Migration Guide

### From Static Processors

1. **Backup Current Config**: Save existing processor configuration
2. **Create Rules**: Convert static processors to rule-based
3. **Test in Development**: Validate rule matching behavior
4. **Gradual Rollout**: Deploy to staging before production
5. **Monitor Metrics**: Ensure email processing continues

### Example Migration

**Before (Static)**:
```bash
worker.processors.0.type=smtpcom_api
worker.processors.0.api_key=key123
worker.processors.0.channel=prod
```

**After (Rule-Based)**:
```json
{
  "rules": [
    {"name": "default", "conditions": {}, "processors": ["smtpcom_prod"]}
  ],
  "processors": {
    "smtpcom_prod": {"type": "smtpcom_api", "api_key": "key123", "channel": "prod"}
  }
}
```

## API Reference

### RuleEngine Class

#### Constructor
```python
RuleEngine(parameter_name: str, region: str = 'us-east-1')
```

#### Methods

##### load_rules() -> bool
Load rules from AWS Parameter Store.

**Returns**: `True` if successful, `False` on error

##### match_email(envelope, message: EmailMessage) -> List[str]
Match email against rules and return processor names.

**Parameters**:
- `envelope`: Email envelope with `mail_from` and `rcpt_tos`
- `message`: EmailMessage object

**Returns**: List of processor names to use

##### get_processor_config(processor_name: str) -> Optional[Dict]
Get processor configuration by name.

**Returns**: Processor config dict or `None` if not found

##### create_processors(processor_names: List[str]) -> List
Create processor instances from names.

**Returns**: List of instantiated processor objects

## Future Enhancements

See [RULE_ENGINE_ROADMAP.md](RULE_ENGINE_ROADMAP.md) for planned features and enhancements.
