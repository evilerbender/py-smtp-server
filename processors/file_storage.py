#!/usr/bin/env python3
"""
File storage email processor
"""

import os
import asyncio
from datetime import datetime
from pathlib import Path
from email.message import EmailMessage
from .base import EmailProcessor


class FileStorageProcessor(EmailProcessor):
    """Store emails as files on disk"""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.storage_dir = Path(self.config.get('storage_dir', '/var/spool/mail'))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    async def process(self, envelope, message: EmailMessage) -> bool:
        """Store email as file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            filename = f"{timestamp}.eml"
            filepath = self.storage_dir / filename
            
            # Write email to file asynchronously
            await asyncio.to_thread(self._write_file, filepath, message)
            return True
        except Exception:
            return False
    
    def _write_file(self, filepath: Path, message: EmailMessage):
        """Write email message to file"""
        with open(filepath, 'w') as f:
            # Write the complete email message as RFC822 format
            f.write(message.as_string())
    
    def get_name(self) -> str:
        return "FileStorage"
