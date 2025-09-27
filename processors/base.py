#!/usr/bin/env python3
"""
Base email processor interface
"""

from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Dict, Any


class EmailProcessor(ABC):
    """Base class for email processors"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
    
    @abstractmethod
    async def process(self, envelope: Any, message: EmailMessage) -> bool:
        """
        Process an email message
        
        Args:
            envelope: SMTP envelope data
            message: Parsed email message
            
        Returns:
            bool: True if processing succeeded, False otherwise
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return processor name for logging"""
        pass
    
    @classmethod
    @abstractmethod
    def get_config_spec(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get configuration specification for this processor
        
        Returns:
            Dict with config keys and their specifications:
            {
                "config_key": {
                    "type": "string|int|bool|email|url",
                    "required": True|False,
                    "description": "Human readable description",
                    "default": "optional default value"
                }
            }
        """
        pass
