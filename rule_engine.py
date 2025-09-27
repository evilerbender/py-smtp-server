#!/usr/bin/env python3
"""
Rule-based email routing engine with AWS Parameter Store integration
"""

import json
import logging
import boto3
from typing import Dict, List, Any, Optional
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class RuleEngine:
    """
    Rule-based email routing engine
    
    Loads routing rules from AWS Parameter Store and matches emails
    against conditions to determine which processors should handle them.
    """
    
    def __init__(self, parameter_name: str, region: str = 'us-east-1'):
        """
        Initialize rule engine
        
        Args:
            parameter_name: AWS Parameter Store parameter name containing rules
            region: AWS region for Parameter Store
        """
        self.parameter_name = parameter_name
        self.region = region
        self.ssm_client = boto3.client('ssm', region_name=region)
        self.rules = []
        self.processors = {}
        
    def load_rules(self) -> bool:
        """
        Load rules from AWS Parameter Store
        
        Returns:
            bool: True if rules loaded successfully
        """
        try:
            response = self.ssm_client.get_parameter(
                Name=self.parameter_name,
                WithDecryption=True
            )
            
            config = json.loads(response['Parameter']['Value'])
            self.rules = config.get('rules', [])
            self.processors = config.get('processors', {})
            
            logger.info(f"Loaded {len(self.rules)} rules and {len(self.processors)} processors")
            return True
            
        except self.ssm_client.exceptions.ParameterNotFound:
            logger.error(f"Parameter '{self.parameter_name}' not found in Parameter Store")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in parameter '{self.parameter_name}': {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load rules from Parameter Store: {e}")
            return False
    
    def match_email(self, envelope, message: EmailMessage) -> List[str]:
        """
        Match email against rules and return processor names
        
        Args:
            envelope: Email envelope with mail_from and rcpt_tos
            message: Email message object
            
        Returns:
            List[str]: List of processor names to use
        """
        # Extract email metadata for matching
        from_email = envelope.mail_from
        from_domain = from_email.split('@')[1] if '@' in from_email else ''
        to_emails = envelope.rcpt_tos
        to_domains = [email.split('@')[1] if '@' in email else '' for email in to_emails]
        
        subject = message.get('Subject', '')
        headers = dict(message.items())
        
        # Match against rules in order
        for rule in self.rules:
            if self._match_rule(rule, from_email, from_domain, to_emails, to_domains, subject, headers):
                processors = rule.get('processors', [])
                logger.info(f"Email matched rule '{rule.get('name', 'unnamed')}', using processors: {processors}")
                return processors
        
        # No rules matched
        logger.warning("No rules matched email, no processors selected")
        return []
    
    def _match_rule(self, rule: Dict, from_email: str, from_domain: str, 
                   to_emails: List[str], to_domains: List[str], 
                   subject: str, headers: Dict) -> bool:
        """
        Check if email matches rule conditions
        
        Args:
            rule: Rule configuration
            from_email: Sender email address
            from_domain: Sender domain
            to_emails: List of recipient email addresses
            to_domains: List of recipient domains
            subject: Email subject
            headers: Email headers dict
            
        Returns:
            bool: True if email matches rule
        """
        conditions = rule.get('conditions', {})
        
        # Empty conditions match everything (default rule)
        if not conditions:
            return True
        
        # Check from_email condition
        if 'from_email' in conditions:
            if from_email != conditions['from_email']:
                return False
        
        # Check from_domain condition
        if 'from_domain' in conditions:
            expected_domain = conditions['from_domain']
            if isinstance(expected_domain, list):
                if from_domain not in expected_domain:
                    return False
            else:
                if from_domain != expected_domain:
                    return False
        
        # Check to_email condition (any recipient must match)
        if 'to_email' in conditions:
            expected_email = conditions['to_email']
            if isinstance(expected_email, list):
                if not any(email in expected_email for email in to_emails):
                    return False
            else:
                if expected_email not in to_emails:
                    return False
        
        # Check to_domain condition (any recipient domain must match)
        if 'to_domain' in conditions:
            expected_domain = conditions['to_domain']
            if isinstance(expected_domain, list):
                if not any(domain in expected_domain for domain in to_domains):
                    return False
            else:
                if expected_domain not in to_domains:
                    return False
        
        # Check subject_contains condition
        if 'subject_contains' in conditions:
            search_text = conditions['subject_contains']
            if isinstance(search_text, list):
                if not any(text.lower() in subject.lower() for text in search_text):
                    return False
            else:
                if search_text.lower() not in subject.lower():
                    return False
        
        # Check header_exists condition
        if 'header_exists' in conditions:
            required_header = conditions['header_exists']
            if isinstance(required_header, list):
                if not any(header in headers for header in required_header):
                    return False
            else:
                if required_header not in headers:
                    return False
        
        # Check header_value condition
        if 'header_value' in conditions:
            for header_name, expected_value in conditions['header_value'].items():
                actual_value = headers.get(header_name, '')
                if isinstance(expected_value, list):
                    if actual_value not in expected_value:
                        return False
                else:
                    if actual_value != expected_value:
                        return False
        
        # All conditions matched
        return True
    
    def get_processor_config(self, processor_name: str) -> Optional[Dict]:
        """
        Get processor configuration by name
        
        Args:
            processor_name: Name of processor
            
        Returns:
            Dict: Processor configuration or None if not found
        """
        return self.processors.get(processor_name)
    
    def create_processors(self, processor_names: List[str]) -> List:
        """
        Create processor instances from names
        
        Args:
            processor_names: List of processor names to create
            
        Returns:
            List: List of instantiated processor objects
        """
        processors = []
        
        for name in processor_names:
            config = self.get_processor_config(name)
            if not config:
                logger.error(f"Processor '{name}' not found in configuration")
                continue
            
            processor_type = config.get('type')
            processor_config = {k: v for k, v in config.items() if k != 'type'}
            
            try:
                if processor_type == 'file_storage':
                    from processors import FileStorageProcessor
                    processors.append(FileStorageProcessor(processor_config))
                elif processor_type == 's3_storage':
                    from processors import S3StorageProcessor
                    processors.append(S3StorageProcessor(processor_config))
                elif processor_type == 'ses_forwarder':
                    from processors import SESForwarderProcessor
                    processors.append(SESForwarderProcessor(processor_config))
                elif processor_type == 'smtpcom_api':
                    from processors import SMTPComAPIProcessor
                    processors.append(SMTPComAPIProcessor(processor_config))
                else:
                    logger.error(f"Unknown processor type: {processor_type}")
                    
            except Exception as e:
                logger.error(f"Failed to create processor '{name}': {e}")
        
        return processors
