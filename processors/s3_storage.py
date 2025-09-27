#!/usr/bin/env python3
"""
S3 storage email processor
"""

from datetime import datetime
from email.message import EmailMessage
from .base import EmailProcessor

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


class S3StorageProcessor(EmailProcessor):
    """Store emails in AWS S3"""
    
    def __init__(self, config=None):
        super().__init__(config)
        if not HAS_BOTO3:
            raise ImportError("boto3 required for S3StorageProcessor")
        
        self.bucket = self.config.get('bucket')
        self.prefix = self.config.get('prefix', 'emails/')
        
        if not self.bucket:
            raise ValueError("S3 bucket name required")
        
        self.s3_client = boto3.client('s3')
    
    async def process(self, envelope, message: EmailMessage) -> bool:
        """Store email in S3"""
        try:
            timestamp = datetime.now().strftime('%Y/%m/%d/%H%M%S_%f')
            key = f"{self.prefix}{timestamp}.eml"
            
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=str(message),
                ContentType='message/rfc822'
            )
            return True
        except Exception:
            return False
    
    def get_name(self) -> str:
        return "S3Storage"
