#!/usr/bin/env python3
"""
Configuration for SMTP server
"""

import os
import json

# Server configuration
SMTP_HOST = os.getenv('SMTP_HOST', '0.0.0.0')
SMTP_PORT = int(os.getenv('SMTP_PORT', '8025'))

# Logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Email processor configuration from environment
def load_processors():
    """Load processor configuration from environment variable"""
    processors_json = os.getenv('EMAIL_PROCESSORS', '[{"type": "file_storage", "config": {"storage_dir": "./emails"}}]')
    try:
        return json.loads(processors_json)
    except json.JSONDecodeError:
        # Fallback to default if JSON is invalid
        return [{'type': 'file_storage', 'config': {'storage_dir': './emails'}}]

EMAIL_PROCESSORS = load_processors()
