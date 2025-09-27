#!/usr/bin/env python3
"""
SQS queue processor for SMTP server
"""

import json
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from .base import EmailProcessor

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


class SQSQueueProcessor(EmailProcessor):
    """Queue emails to SQS for async processing"""
    
    def __init__(self, config=None):
        super().__init__(config)
        if not HAS_BOTO3:
            raise ImportError("boto3 required for SQSQueueProcessor")
        
        self.queue_url = self.config.get('queue_url')
        if not self.queue_url:
            raise ValueError("queue_url required for SQS processor")
        
        self.sqs_client = boto3.client('sqs')
    
    async def process(self, envelope, message: EmailMessage) -> bool:
        """Queue email to SQS"""
        try:
            # Extract message body properly for multipart messages
            body_text = self._extract_body(message)
            
            # Create message payload
            email_data = {
                'id': str(uuid.uuid4()),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'envelope': {
                    'mail_from': envelope.mail_from,
                    'rcpt_tos': envelope.rcpt_tos
                },
                'message': {
                    'subject': message.get('Subject', ''),
                    'from': message.get('From', ''),
                    'to': message.get('To', ''),
                    'headers': dict(message.items()),
                    'body': body_text,
                    'raw': str(message),
                    'has_attachments': self._has_attachments(message),
                    'size_bytes': len(str(message))
                }
            }
            
            # Check if message is too large for SQS (256KB limit)
            message_size = len(json.dumps(email_data))
            if message_size > 250000:  # Leave some buffer
                # For large messages, could store in S3 and put S3 key in SQS
                return await self._handle_large_message(email_data)
            
            # Send to SQS
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(email_data),
                MessageGroupId=f"{self._extract_domain(envelope.mail_from)}{self._extract_domain(envelope.rcpt_tos[0] if envelope.rcpt_tos else '')}",
                MessageAttributes={
                    'from_domain': {
                        'StringValue': self._extract_domain(envelope.mail_from),
                        'DataType': 'String'
                    },
                    'to_domain': {
                        'StringValue': self._extract_domain(envelope.rcpt_tos[0] if envelope.rcpt_tos else ''),
                        'DataType': 'String'
                    },
                    'message_id': {
                        'StringValue': email_data['id'],
                        'DataType': 'String'
                    },
                    'has_attachments': {
                        'StringValue': str(email_data['message']['has_attachments']),
                        'DataType': 'String'
                    }
                }
            )
            return True
        except Exception:
            return False
    
    def _extract_body(self, message: EmailMessage) -> str:
        """Extract text body from potentially multipart message"""
        if message.is_multipart():
            # Find the first text/plain part
            for part in message.walk():
                if part.get_content_type() == 'text/plain':
                    return part.get_payload(decode=True).decode('utf-8', errors='ignore')
            return "Multipart message with no text/plain part"
        else:
            return str(message.get_payload())
    
    def _has_attachments(self, message: EmailMessage) -> bool:
        """Check if message has attachments"""
        if not message.is_multipart():
            return False
        
        for part in message.walk():
            if part.get_content_disposition() == 'attachment':
                return True
        return False
    
    async def _handle_large_message(self, email_data):
        """Handle messages too large for SQS (future: store in S3)"""
        # For now, just log and fail
        # TODO: Implement S3 storage for large messages
        return False
    
    def _extract_domain(self, email_address):
        """Extract domain from email address"""
        if '@' in email_address:
            return email_address.split('@')[1]
        return 'unknown'
    
    def get_name(self) -> str:
        return "SQSQueue"
