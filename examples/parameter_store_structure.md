# AWS Parameter Store Structure for Email Routing

## Parameter Hierarchy

```
/smtp-server/
├── config/
│   ├── routing-rules          # JSON configuration (SecureString)
│   ├── default-processors     # JSON array of default processors
│   └── version               # Configuration version for cache invalidation
├── processors/
│   ├── smtpcom-api-key       # SMTP.com API key (SecureString)
│   ├── s3-bucket-name        # S3 bucket for storage
│   └── ses-from-email        # SES sender email
└── rules/
    ├── support-urgent/
    │   ├── enabled           # true/false
    │   ├── priority          # 10
    │   └── conditions        # JSON conditions object
    └── marketing-s3/
        ├── enabled           # true/false
        ├── priority          # 20
        └── conditions        # JSON conditions object
```

## Parameter Examples

### Main Configuration
```bash
# Store complete routing rules
aws ssm put-parameter \
  --name "/smtp-server/config/routing-rules" \
  --type "SecureString" \
  --value "$(cat routing_rules_example.json)"

# Version for cache invalidation
aws ssm put-parameter \
  --name "/smtp-server/config/version" \
  --type "String" \
  --value "1.0.0"
```

### Sensitive Configuration
```bash
# SMTP.com API key
aws ssm put-parameter \
  --name "/smtp-server/processors/smtpcom-api-key" \
  --type "SecureString" \
  --value "your-secret-api-key"

# S3 bucket name
aws ssm put-parameter \
  --name "/smtp-server/processors/s3-bucket-name" \
  --type "String" \
  --value "my-email-storage-bucket"
```

### Individual Rule Management
```bash
# Enable/disable specific rules
aws ssm put-parameter \
  --name "/smtp-server/rules/support-urgent/enabled" \
  --type "String" \
  --value "true"

# Update rule priority
aws ssm put-parameter \
  --name "/smtp-server/rules/support-urgent/priority" \
  --type "String" \
  --value "5"
```

## Configuration Loading Strategy

1. **Hierarchical Loading**: Load from most specific to general
2. **Caching**: Cache parameters with TTL and version checking
3. **Hot Reload**: Watch for parameter changes via CloudWatch Events
4. **Fallback**: Use local .env if Parameter Store unavailable
5. **Encryption**: Use SecureString for sensitive values

## Benefits

- **Centralized Management**: All configuration in one place
- **Security**: Encrypted storage for sensitive values
- **Versioning**: Built-in parameter versioning
- **Access Control**: IAM-based access control
- **Audit Trail**: CloudTrail logging of all changes
- **Cross-Environment**: Different parameter paths per environment
