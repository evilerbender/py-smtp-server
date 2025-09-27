#!/usr/bin/env python3
"""
Hybrid SQS+S3 processor for handling emails of any size
"""

import json
import uuid
from datetime import datetime
from email.message import EmailMessage
from .base import EmailProcessor

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


class SQSS3HybridProcessor(EmailProcessor):
    """Store emails in S3 and queue metadata in SQS"""
    
    def __init__(self, config=None):
        super().__init__(config)
        if not HAS_BOTO3:
            raise ImportError("boto3 required for SQSs3HybridProcessor")
        
        self.queue_url = self.config.get('queue_url')
        self.s3_bucket = self.config.get('s3_bucket')
        self.s3_prefix = self.config.get('s3_prefix', 'emails/')
        
        if not self.queue_url:
            raise ValueError("queue_url required for SQS+S3 processor")
        if not self.s3_bucket:
            raise ValueError("s3_bucket required for SQS+S3 processor")
        
        self.sqs_client = boto3.client('sqs')
        self.s3_client = boto3.client('s3')
    
    async def process(self, envelope, message: EmailMessage) -> bool:
        """Store email in S3 and queue metadata in SQS"""
        try:
            message_id = str(uuid.uuid4())
            timestamp = datetime.utcnow()
            
            # Create S3 key with well-known structure
            s3_key = self._generate_s3_key(timestamp, message_id, envelope)
            
            # Store complete email in S3
            s3_success = await self._store_email_in_s3(s3_key, message)
            if not s3_success:
                return False
            
            # Create lightweight SQS message with metadata and S3 reference
            sqs_message = {
                'id': message_id,
                'timestamp': timestamp.isoformat(),
                'envelope': {
                    'mail_from': envelope.mail_from,
                    'rcpt_tos': envelope.rcpt_tos
                },
                'headers': {
                    'subject': message.get('Subject', ''),
                    'from': message.get('From', ''),
                    'to': message.get('To', ''),
                    'date': message.get('Date', ''),
                    'message_id': message.get('Message-ID', '')
                },
                'metadata': {
                    'has_attachments': self._has_attachments(message),
                    'is_multipart': message.is_multipart(),
                    'content_type': message.get_content_type(),
                    'size_bytes': len(str(message))
                },
                's3_reference': {
                    'bucket': self.s3_bucket,
                    'key': s3_key,
                    'region': self.s3_client.meta.region_name
                }
            }
            
            # Send lightweight message to SQS
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(sqs_message),
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
                        'StringValue': message_id,
                        'DataType': 'String'
                    },
                    'has_attachments': {
                        'StringValue': str(sqs_message['metadata']['has_attachments']),
                        'DataType': 'String'
                    },
                    's3_bucket': {
                        'StringValue': self.s3_bucket,
                        'DataType': 'String'
                    },
                    's3_key': {
                        'StringValue': s3_key,
                        'DataType': 'String'
                    }
                }
            )
            return True
        except Exception as e:
            # Log detailed error information for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"SQS+S3 Hybrid processor failed: {e}")
            logger.error(f"Queue URL: {self.queue_url}")
            logger.error(f"S3 Bucket: {self.s3_bucket}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def _generate_s3_key(self, timestamp, message_id, envelope):
        """Generate well-known S3 key structure"""
        # Structure: emails/YYYY/MM/DD/HH/from_domain/message_id.eml
        from_domain = self._extract_domain(envelope.mail_from)
        
        key = (
            f"{self.s3_prefix}"
            f"{timestamp.strftime('%Y/%m/%d/%H')}/"
            f"{from_domain}/"
            f"{message_id}.eml"
        )
        return key
    
    async def _store_email_in_s3(self, s3_key, message):
        """Store complete email in S3"""
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=message.as_string(),
                ContentType='message/rfc822',
                Metadata={
                    'subject': message.get('Subject', '')[:1000],  # Truncate for metadata limits
                    'from': message.get('From', '')[:1000],
                    'to': message.get('To', '')[:1000]
                }
            )
            return True
        except Exception:
            return False
    
    def _has_attachments(self, message: EmailMessage) -> bool:
        """Check if message has attachments"""
        if not message.is_multipart():
            return False
        
        for part in message.walk():
            if part.get_content_disposition() == 'attachment':
                return True
        return False
    
    def _extract_domain(self, email_address):
        """Extract domain from email address"""
        if '@' in email_address:
            return email_address.split('@')[1]
        return 'unknown'
    
    def get_name(self) -> str:
        return "SQSs3Hybrid"
