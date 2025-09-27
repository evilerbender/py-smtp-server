#!/usr/bin/env python3
"""
SQS worker service for processing queued emails

This module implements a worker service that polls AWS SQS queues for
email messages and processes them through configured processors. It's
designed to work as part of a decoupled email processing architecture
where SMTP servers queue emails and workers process them asynchronously.

Architecture:
    SQS Queue -> Worker -> Processors -> (S3 | SES | SMTP.com | File)

Key Features:
    - Long polling for efficient SQS message retrieval
    - Batch processing of up to 10 messages at once
    - Automatic message deletion on successful processing
    - Graceful error handling and logging
    - Systemd integration with signal handling
    - Email message reconstruction from JSON payload
"""

import asyncio
import json
import logging
import signal
import sys
from email.message import EmailMessage

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, rely on system environment
    pass

# Import AWS SDK with fallback handling
try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

# Import configuration with fallback
try:
    from config import LOG_LEVEL
except ImportError:
    LOG_LEVEL = 'INFO'

logger = logging.getLogger(__name__)


class EmailEnvelope:
    """
    Mock envelope for compatibility with processors
    
    This class provides a simple container for SMTP envelope data
    that's compatible with the processor interface. It reconstructs
    the envelope information from the SQS message payload.
    """
    
    def __init__(self, mail_from, rcpt_tos):
        """
        Initialize email envelope
        
        Args:
            mail_from (str): Sender email address
            rcpt_tos (list): List of recipient email addresses
        """
        self.mail_from = mail_from
        self.rcpt_tos = rcpt_tos


class SQSWorker:
    """
    SQS worker for processing queued emails
    
    This class implements a worker that continuously polls an SQS queue
    for email messages, processes them through configured processors,
    and manages message lifecycle (deletion on success, retry on failure).
    
    The worker uses long polling to efficiently retrieve messages and
    processes them in batches for better throughput.
    """
    
    def __init__(self, queue_url, processors=None, rule_engine=None):
        """
        Initialize SQS worker
        
        Args:
            queue_url (str): Full SQS queue URL to poll
            processors (list, optional): List of EmailProcessor instances (legacy mode)
            rule_engine (RuleEngine, optional): Rule engine for conditional routing
            
        Raises:
            ImportError: If boto3 is not available
        """
        if not HAS_BOTO3:
            raise ImportError("boto3 required for SQS worker")
        
        self.queue_url = queue_url
        self.processors = processors or []
        self.rule_engine = rule_engine
        self.sqs_client = boto3.client('sqs')
        self.s3_client = boto3.client('s3')
        self.running = False
        
        # Load rules if rule engine is provided
        if self.rule_engine:
            self.rule_engine.load_rules()
            logger.info("Rule-based routing enabled")
        else:
            logger.info(f"Legacy mode with {len(self.processors)} static processors")
    
    def start(self):
        """
        Start the worker
        
        Initializes the worker state and logs startup information.
        The actual polling loop is started by calling run_forever().
        """
        self.running = True
        logger.info(f"SQS worker started, polling queue: {self.queue_url}")
        logger.info(f"Configured processors: {len(self.processors)}")
    
    def stop(self):
        """
        Stop the worker gracefully
        
        Sets the running flag to False, which will cause the polling
        loop to exit after the current iteration completes.
        """
        self.running = False
        logger.info("SQS worker stopped")
    
    async def run_forever(self):
        """
        Run worker until stopped
        
        Main worker loop that continuously polls SQS for messages
        and processes them. Includes error handling and backoff
        logic for resilient operation.
        
        The loop continues until self.running is set to False,
        typically by a signal handler.
        """
        while self.running:
            try:
                # Poll for messages and process them
                await self._poll_messages()
                
                # Brief pause between polling cycles
                await asyncio.sleep(1)
            except Exception as e:
                # Log errors and continue with longer backoff
                logger.error(f"Error in worker loop: {e}")
                await asyncio.sleep(5)  # Longer pause on error
    
    async def _poll_messages(self):
        """
        Poll SQS for messages and process them
        
        Uses SQS long polling to efficiently retrieve messages.
        Processes up to 10 messages per call to improve throughput
        while maintaining reasonable memory usage.
        
        Long polling (20 seconds) reduces API calls and improves
        efficiency compared to short polling.
        """
        try:
            # Poll SQS with long polling for efficiency
            response = self.sqs_client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=10,      # Process up to 10 messages at once
                WaitTimeSeconds=20,          # Long polling for efficiency
                MessageAttributeNames=['All'] # Include all message attributes
            )
            
            # Process each message in the batch
            messages = response.get('Messages', [])
            for message in messages:
                await self._process_message(message)
                
        except Exception as e:
            logger.error(f"Error polling SQS: {e}")
    
    async def _process_message(self, sqs_message):
        """
        Process a single SQS message
        
        Handles both SMTP server messages and SES notifications.
        Parses the JSON message body, reconstructs the email message
        and envelope, processes through all configured processors,
        and deletes the message on success.
        
        Args:
            sqs_message (dict): SQS message with Body and ReceiptHandle
        """
        try:
            # Parse the JSON message body
            message_data = json.loads(sqs_message['Body'])
            
            # Detect message type and route accordingly
            if self._is_ses_notification(message_data):
                await self._process_ses_notification(sqs_message, message_data)
            else:
                await self._process_smtp_message(sqs_message, message_data)
                
        except json.JSONDecodeError as e:
            logger.error(f"Malformed JSON message, deleting from queue: {e}")
            logger.debug(f"Message body: {sqs_message['Body'][:200]}...")
            # Delete malformed message to prevent infinite reprocessing
            await self._delete_message(sqs_message)
        except KeyError as e:
            logger.error(f"Missing required field in message, deleting from queue: {e}")
            logger.debug(f"Message data: {sqs_message.get('Body', 'No body')[:200]}...")
            # Delete message with missing required fields
            await self._delete_message(sqs_message)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Don't delete on general errors - might be temporary issues
    
    async def _delete_message(self, sqs_message):
        """
        Delete a message from the SQS queue
        
        Args:
            sqs_message (dict): SQS message to delete
        """
        try:
            self.sqs_client.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=sqs_message['ReceiptHandle']
            )
            logger.debug(f"Deleted malformed message from queue")
        except Exception as e:
            logger.error(f"Failed to delete malformed message: {e}")
    
    def _is_ses_notification(self, message_data):
        """
        Detect if message is an SES notification
        
        Args:
            message_data (dict): Parsed message body
            
        Returns:
            bool: True if this is an SES notification
        """
        # SES notifications have Type and Message fields
        return (message_data.get('Type') == 'Notification' and 
                'Message' in message_data)
    
    async def _process_ses_notification(self, sqs_message, message_data):
        """
        Process SES notification message
        
        Args:
            sqs_message (dict): SQS message
            message_data (dict): Parsed message body
        """
        try:
            # Parse the nested SES message
            ses_message = json.loads(message_data['Message'])
            
            # Extract S3 object information
            if 'receipt' not in ses_message or 'action' not in ses_message['receipt']:
                logger.error("SES notification missing receipt/action information")
                return
                
            action = ses_message['receipt']['action']
            if action.get('type') != 'S3':
                logger.error(f"Unsupported SES action type: {action.get('type')}")
                return
            
            bucket_name = action.get('bucketName')
            object_key = action.get('objectKey')
            
            if not bucket_name or not object_key:
                logger.error("SES notification missing S3 bucket/key information")
                return
            
            # Retrieve email from S3
            try:
                s3_response = self.s3_client.get_object(Bucket=bucket_name, Key=object_key)
                email_content = s3_response['Body'].read()
                
                # Parse email message
                from email import message_from_bytes
                email_msg = message_from_bytes(email_content)
                
                # Create envelope from SES data
                mail_data = ses_message.get('mail', {})
                envelope = EmailEnvelope(
                    mail_data.get('source', ''),
                    mail_data.get('destination', [])
                )
                
                # Process through configured processors
                message_id = mail_data.get('messageId', 'unknown')
                success = await self._process_email(envelope, email_msg, message_id)
                
                if success:
                    # Delete the SQS message
                    self.sqs_client.delete_message(
                        QueueUrl=self.queue_url,
                        ReceiptHandle=sqs_message['ReceiptHandle']
                    )
                    logger.info(f"SES email {message_id} processed and deleted from queue")
                else:
                    logger.warning(f"SES email {message_id} processing failed")
                    
            except Exception as e:
                logger.error(f"Failed to retrieve email from S3 {bucket_name}/{object_key}: {e}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse SES message JSON: {e}")
        except Exception as e:
            logger.error(f"Error processing SES notification: {e}")
    
    async def _process_smtp_message(self, sqs_message, message_data):
        """
        Process SMTP server message (existing logic)
        
        Args:
            sqs_message (dict): SQS message
            message_data (dict): Parsed message body
        """
        try:
            # Check if this is a hybrid S3 message
            if 's3_reference' in message_data:
                email_msg = await self._reconstruct_from_s3(message_data)
            else:
                # Legacy direct message format
                email_msg = self._reconstruct_from_message_data(message_data)
            
            if not email_msg:
                logger.error(f"Failed to reconstruct email from message")
                return
            
            # Create envelope object for processor compatibility
            envelope = EmailEnvelope(
                message_data['envelope']['mail_from'],
                message_data['envelope']['rcpt_tos']
            )
            
            # Process through all configured processors
            success = await self._process_email(envelope, email_msg, message_data['id'])
            
            if success:
                # Delete message from queue on successful processing
                self.sqs_client.delete_message(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=sqs_message['ReceiptHandle']
                )
                logger.info(f"Successfully processed email {message_data['id']}")
            else:
                # Leave message in queue for retry (will become visible again
                # after visibility timeout expires)
                logger.warning(f"Failed to process email {message_data['id']}")
                
        except Exception as e:
            logger.error(f"Error processing SMTP message: {e}")
    
    async def _reconstruct_from_s3(self, email_data):
        """Reconstruct email from S3 reference"""
        try:
            s3_ref = email_data['s3_reference']
            
            # Retrieve complete email from S3
            response = self.s3_client.get_object(
                Bucket=s3_ref['bucket'],
                Key=s3_ref['key']
            )
            
            # Parse the complete RFC822 message
            email_content = response['Body'].read().decode('utf-8')
            from email import message_from_string
            return message_from_string(email_content)
            
        except Exception as e:
            logger.error(f"Failed to retrieve email from S3: {e}")
            return None
    
    def _reconstruct_from_message_data(self, email_data):
        """Reconstruct email from direct message data (legacy)"""
        try:
            # Reconstruct EmailMessage object from JSON data
            email_msg = EmailMessage()
            email_msg['Subject'] = email_data['message']['subject']
            email_msg['From'] = email_data['message']['from']
            email_msg['To'] = email_data['message']['to']
            
            # Add other headers (excluding the ones we already set)
            for key, value in email_data['message']['headers'].items():
                if key.lower() not in ['subject', 'from', 'to']:
                    email_msg[key] = value
            
            # Set the message body content
            email_msg.set_content(email_data['message']['body'])
            return email_msg
            
        except Exception as e:
            logger.error(f"Failed to reconstruct email from message data: {e}")
            return None
    
    async def _process_email(self, envelope, message, message_id):
        """
        Process email through configured processors or rule-based routing
        
        Routes the email through processors based on rules (if rule engine enabled)
        or through all static processors (legacy mode). Processors operate 
        independently - failure in one doesn't prevent others from running.
        
        Args:
            envelope (EmailEnvelope): SMTP envelope data
            message (EmailMessage): Reconstructed email message
            message_id (str): Unique message identifier for logging
            
        Returns:
            bool: True if at least one processor succeeded, False otherwise
        """
        success_count = 0
        
        # Determine which processors to use
        if self.rule_engine:
            # Rule-based routing
            processor_names = self.rule_engine.match_email(envelope, message)
            if not processor_names:
                logger.warning(f"No processors matched for email {message_id}")
                return False
            
            processors = self.rule_engine.create_processors(processor_names)
        else:
            # Legacy mode - use all static processors
            processors = self.processors
        
        for processor in processors:
            try:
                # Process email through this processor
                result = await processor.process(envelope, message)
                if result:
                    success_count += 1
                    logger.info(f"Email {message_id} processed by {processor.get_name()}")
                else:
                    logger.warning(f"Email {message_id} failed in {processor.get_name()}")
            except Exception as e:
                # Log processor errors but continue with others
                logger.error(f"Error in processor {processor.get_name()}: {e}")
        
        # Consider processing successful if at least one processor succeeded
        return success_count > 0


def create_worker_processors():
    """
    Create processors for worker from environment configuration
    
    Loads processor configuration from dot-notation environment variables.
    
    Returns:
        list: List of instantiated EmailProcessor objects
    """
    import os
    from config_parser import load_processors
    
    processors = []
    
    # Load processors using dot-notation parser
    processor_configs = load_processors('worker')
    
    for config in processor_configs:
        processor_type = config.get('type')
        processor_config = config.get('config', {})
        
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
                logger.warning(f"Unknown processor type: {processor_type}")
        except Exception as e:
            logger.error(f"Failed to create {processor_type} processor: {e}")
    
    if not processors:
        logger.warning("No processors configured, emails will be processed but not forwarded")
    
    return processors


def setup_logging():
    """
    Setup logging configuration for systemd deployment
    
    Configures Python logging to output to stdout with a structured
    format suitable for systemd/journald ingestion. Uses the same
    format as the SMTP server for consistency.
    """
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )


def main():
    """
    Main entry point for SQS worker
    
    Sets up logging, validates configuration, creates the worker,
    registers signal handlers, and runs the worker until terminated.
    
    Environment Variables:
        SQS_QUEUE_URL: Required SQS queue URL to poll
        LOG_LEVEL: Logging level (default: INFO)
        RULE_ENGINE_PARAMETER: AWS Parameter Store parameter for rules (optional)
        AWS_REGION: AWS region for Parameter Store (default: us-east-1)
        
    Signal Handling:
        SIGTERM: Graceful shutdown (systemd stop)
        SIGINT: Graceful shutdown (Ctrl+C)
        
    Exit Codes:
        0: Normal shutdown
        1: Fatal error (missing config, startup failure, etc.)
    """
    # Initialize logging for systemd
    setup_logging()
    
    # Get required configuration from environment
    import os
    queue_url = os.getenv('SQS_QUEUE_URL')
    if not queue_url:
        logger.error("SQS_QUEUE_URL environment variable required")
        sys.exit(1)
    
    # Check for rule-based routing configuration
    rule_parameter = os.getenv('RULE_ENGINE_PARAMETER')
    rule_engine = None
    
    if rule_parameter:
        # Use rule-based routing
        region = os.getenv('AWS_REGION', 'us-east-1')
        try:
            from rule_engine import RuleEngine
            rule_engine = RuleEngine(rule_parameter, region)
            logger.info(f"Rule-based routing enabled with parameter: {rule_parameter}")
        except Exception as e:
            logger.error(f"Failed to initialize rule engine: {e}")
            sys.exit(1)
        
        worker = SQSWorker(queue_url, rule_engine=rule_engine)
    else:
        # Use legacy static processors
        processors = create_worker_processors()
        worker = SQSWorker(queue_url, processors)
    
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down...")
        worker.stop()
        sys.exit(0)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)  # systemd stop
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    
    async def run_worker():
        """
        Async wrapper for worker execution
        
        Handles worker startup, runs the main polling loop, and
        ensures proper cleanup on exit or error.
        """
        try:
            # Start the worker
            worker.start()
            
            # Run the main polling loop
            await worker.run_forever()
        except Exception as e:
            # Log fatal errors and ensure cleanup
            logger.error(f"Worker error: {e}")
            worker.stop()
            raise
    
    try:
        # Run the async worker
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        logger.info("Received keyboard interrupt")
    except Exception as e:
        # Handle fatal errors
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        # Ensure worker is stopped
        worker.stop()


if __name__ == '__main__':
    main()
