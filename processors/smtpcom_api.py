#!/usr/bin/env python3
"""
SMTP.com API email processor
"""

import json
import logging
from email.message import EmailMessage
from typing import Dict, Any
from .base import EmailProcessor

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class SMTPComAPIProcessor(EmailProcessor):
    """Send emails via SMTP.com API"""
    
    def __init__(self, config=None):
        super().__init__(config)
        if not HAS_REQUESTS:
            raise ImportError("requests required for SMTPComAPIProcessor")
        
        self.api_key = self.config.get('api_key')
        self.channel = self.config.get('channel')
        self.api_url = 'https://api.smtp.com/v4/messages'
        
        if not self.api_key:
            raise ValueError("api_key required for SMTP.com API")
        if not self.channel:
            raise ValueError("channel required for SMTP.com API")
    
    async def process(self, envelope, message: EmailMessage) -> bool:
        """Send email via SMTP.com API"""
        try:
            # Build recipients list
            recipients = {
                "to": [{"address": addr} for addr in envelope.rcpt_tos]
            }
            
            # Extract from email header
            from_header = message.get('From', '')
            from_email = from_header.split('<')[-1].rstrip('>') if '<' in from_header else from_header
            from_name = from_header.split('<')[0].strip().strip('"') if '<' in from_header else ''
            
            # Build originator
            originator = {
                "from": {
                    "address": from_email,
                    "name": from_name
                }
            }
            
            # Extract message content and attachments
            body_parts = []
            attachments = []
            
            if message.is_multipart():
                # Handle multipart messages
                for part in message.walk():
                    content_type = part.get_content_type()
                    content_disposition = part.get('Content-Disposition', '')
                    
                    if content_type in ['text/plain', 'text/html'] and 'attachment' not in content_disposition:
                        # Text content with proper encoding handling
                        content = part.get_payload(decode=True)
                        if isinstance(content, bytes):
                            # Try to get charset from content type
                            charset = part.get_content_charset() or 'utf-8'
                            try:
                                content = content.decode(charset)
                            except (UnicodeDecodeError, LookupError):
                                # Fallback to utf-8 with error handling
                                content = content.decode('utf-8', errors='replace')
                        body_parts.append({
                            "type": content_type,
                            "content": content
                        })
                    elif 'attachment' in content_disposition or part.get_filename():
                        # Attachment
                        filename = part.get_filename() or 'attachment'
                        attachment_content = part.get_payload(decode=True)
                        if attachment_content:
                            import base64
                            attachments.append({
                                "type": part.get_content_type() or "application/octet-stream",
                                "disposition": "attachment",
                                "filename": filename,
                                "encoding": "base64",
                                "content": base64.b64encode(attachment_content).decode('ascii')
                            })
            else:
                # Handle single part messages
                content = message.get_payload(decode=True)
                if isinstance(content, bytes):
                    charset = message.get_content_charset() or 'utf-8'
                    try:
                        content = content.decode(charset)
                    except (UnicodeDecodeError, LookupError):
                        content = content.decode('utf-8', errors='replace')
                else:
                    content = str(content)
                body_parts.append({
                    "type": message.get_content_type(),
                    "content": content
                })
            
            # Build body with parts and attachments
            body = {"parts": body_parts}
            if attachments:
                body["attachments"] = attachments
            
            payload = {
                "channel": self.channel,
                "recipients": recipients,
                "originator": originator,
                "subject": message.get('Subject', ''),
                "body": body
            }
            
            headers = {
                'X-SMTPCOM-API': self.api_key,
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                # Parse response to get message ID for status tracking
                try:
                    response_data = response.json()
                    message_id = response_data.get('data', {}).get('message_id')
                    if message_id:
                        # Log the status URL for tracking
                        status_url = f"https://api.smtp.com/v4/messages/{message_id}"
                        logger.info(f"SMTP.com Status URL: {status_url}")
                        logger.info(f"SMTP.com Message ID: {message_id}")
                        logger.info(f"Status check: curl -H 'X-SMTPCOM-API: <API_KEY>' {status_url}")
                except (json.JSONDecodeError, KeyError):
                    pass
                return True
            else:
                return False
        except Exception:
            return False
    
    def get_name(self) -> str:
        return "SMTPComAPI"
    
    @classmethod
    def get_config_spec(cls) -> Dict[str, Dict[str, Any]]:
        return {
            "api_key": {
                "type": "string",
                "required": True,
                "description": "SMTP.com API key for authentication"
            },
            "channel": {
                "type": "string", 
                "required": True,
                "description": "SMTP.com channel name for sending emails"
            }
        }
