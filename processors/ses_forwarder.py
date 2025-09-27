#!/usr/bin/env python3
"""
SES forwarder email processor
"""

from email.message import EmailMessage
from .base import EmailProcessor

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


class SESForwarderProcessor(EmailProcessor):
    """Forward emails via AWS SES"""
    
    def __init__(self, config=None):
        super().__init__(config)
        if not HAS_BOTO3:
            raise ImportError("boto3 required for SESForwarderProcessor")
        
        self.from_email = self.config.get('from_email')
        self.to_emails = self.config.get('to_emails', [])
        
        if not self.from_email:
            raise ValueError("from_email required for SES forwarding")
        if not self.to_emails:
            raise ValueError("to_emails required for SES forwarding")
        
        self.ses_client = boto3.client('ses')
    
    async def process(self, envelope, message: EmailMessage) -> bool:
        """Forward email via SES"""
        try:
            self.ses_client.send_raw_email(
                Source=self.from_email,
                Destinations=self.to_emails,
                RawMessage={'Data': str(message)}
            )
            return True
        except Exception:
            return False
    
    def get_name(self) -> str:
        return "SESForwarder"
