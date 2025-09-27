#!/usr/bin/env python3
"""
Minimal SMTP server using aiosmtpd for systemd deployment

This module provides a production-ready SMTP server that accepts email
connections and routes messages through a configurable processor system.
The server is designed for deployment as a systemd service in AWS VPC
environments.

Architecture:
    SMTP Server -> Processors -> (SQS Queue | File Storage | API Calls)

Key Features:
    - Async SMTP server using aiosmtpd
    - Modular processor system for email routing
    - Environment-based configuration
    - Systemd integration with proper signal handling
    - Support for multiple concurrent connections
"""

import asyncio
import logging
import signal
import sys
from aiosmtpd.controller import Controller
from email import message_from_bytes

# Import configuration with fallback for development
try:
    from config import SMTP_HOST, SMTP_PORT, LOG_LEVEL
    from config_parser import load_processors
except ImportError:
    # Fallback configuration for development/testing
    SMTP_HOST = 'localhost'
    SMTP_PORT = 8025
    LOG_LEVEL = 'INFO'
    from config_parser import load_processors

logger = logging.getLogger(__name__)


def create_processors():
    """
    Create email processors from configuration
    
    Loads processor configurations from dot-notation environment variables.
    Handles missing dependencies gracefully by logging errors and continuing 
    with available processors.
    
    Returns:
        list: List of instantiated EmailProcessor objects
        
    Raises:
        ImportError: If required processor dependencies are missing
        ValueError: If processor configuration is invalid
        SystemExit: If no processors can be created successfully
    """
    processors = []
    errors = []
    
    # Load processors using dot-notation parser
    processor_configs = load_processors('email')
    
    # Fallback for development if no processors configured
    if not processor_configs:
        processor_configs = [{'type': 'file_storage', 'config': {'storage_dir': './emails'}}]
    
    for proc_config in processor_configs:
        proc_type = proc_config.get('type')
        proc_settings = proc_config.get('config', {})
        
        try:
            # Import and instantiate processors based on type
            if proc_type == 'file_storage':
                from processors import FileStorageProcessor
                processors.append(FileStorageProcessor(proc_settings))
            elif proc_type == 's3_storage':
                from processors import S3StorageProcessor
                processors.append(S3StorageProcessor(proc_settings))
            elif proc_type == 'ses_forwarder':
                from processors import SESForwarderProcessor
                processors.append(SESForwarderProcessor(proc_settings))
            elif proc_type == 'smtpcom_api':
                from processors import SMTPComAPIProcessor
                processors.append(SMTPComAPIProcessor(proc_settings))
            elif proc_type == 'sqs_queue':
                from processors import SQSQueueProcessor
                processors.append(SQSQueueProcessor(proc_settings))
            elif proc_type == 'sqs_s3_hybrid':
                from processors import SQSS3HybridProcessor
                processors.append(SQSS3HybridProcessor(proc_settings))
            else:
                error_msg = f"Unknown processor type: {proc_type}"
                logger.error(error_msg)
                errors.append(error_msg)
        except Exception as e:
            # Log processor creation failures
            error_msg = f"Failed to create processor {proc_type}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
    
    # Fatal error if no processors were created successfully
    if not processors:
        logger.error("FATAL: No email processors could be created successfully")
        logger.error("Processor creation errors:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("Server cannot start without at least one working processor")
        sys.exit(1)
    
    if errors:
        logger.warning(f"Some processors failed to initialize, continuing with {len(processors)} working processors")
    
    return processors


class SMTPHandler:
    """
    Minimal SMTP message handler with modular processors
    
    This class implements the aiosmtpd handler interface to process
    incoming SMTP connections and messages. It routes received emails
    through a configurable set of processors for storage, forwarding,
    or other operations.
    
    The handler accepts all recipients and processes all messages,
    making it suitable for use as a centralized email router in
    VPC environments.
    """
    
    def __init__(self, processors=None):
        """
        Initialize SMTP handler with processors
        
        Args:
            processors (list, optional): List of EmailProcessor instances.
                                       If None, creates processors from config.
        """
        self.processors = processors or []
    
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        """
        Handle SMTP RCPT TO command
        
        This method is called for each recipient address in an SMTP transaction.
        We accept all recipients without validation, making this server suitable
        for use as an internal email router.
        
        Args:
            server: SMTP server instance
            session: SMTP session data
            envelope: Email envelope being built
            address (str): Recipient email address
            rcpt_options: SMTP RCPT command options
            
        Returns:
            str: SMTP response code and message
        """
        # Add recipient to envelope for processing
        envelope.rcpt_tos.append(address)
        return '250 OK'
    
    async def handle_DATA(self, server, session, envelope):
        """
        Handle SMTP DATA command and process email content
        
        This method is called when the SMTP client sends the email content.
        It parses the message, logs key information, and routes the email
        through all configured processors.
        
        Args:
            server: SMTP server instance
            session: SMTP session data
            envelope: Complete email envelope with content
            
        Returns:
            str: SMTP response code and message
        """
        try:
            # Parse the raw email content into a structured message
            msg = message_from_bytes(envelope.content)
            
            # Log email receipt for monitoring and debugging
            logger.info(f"Received email from {envelope.mail_from} to {envelope.rcpt_tos}")
            logger.info(f"Subject: {msg.get('Subject', 'No Subject')}")
            
            # Process email through all configured processors
            await self._process_email(envelope, msg)
            
            # Return success response to SMTP client
            return '250 Message accepted'
        except Exception as e:
            # Log processing errors and return SMTP error response
            logger.error(f"Error processing email: {e}")
            return '550 Error processing message'
    
    async def _process_email(self, envelope, message):
        """
        Process email through all configured processors
        
        Routes the email through each processor in sequence. Processors
        operate independently - failure in one processor doesn't prevent
        others from running. This allows for redundant storage or multiple
        delivery methods.
        
        Args:
            envelope: SMTP envelope with sender and recipient information
            message (EmailMessage): Parsed email message object
        """
        for processor in self.processors:
            try:
                # Process email and check success status
                success = await processor.process(envelope, message)
                if success:
                    logger.info(f"Email processed successfully by {processor.get_name()}")
                else:
                    logger.warning(f"Email processing failed in {processor.get_name()}")
            except Exception as e:
                # Log processor errors but continue with remaining processors
                logger.error(f"Error in processor {processor.get_name()}: {e}")


class SMTPServerManager:
    """
    Manages SMTP server lifecycle for systemd deployment
    
    This class handles the complete lifecycle of the SMTP server including
    startup, shutdown, and graceful handling of system signals. It's designed
    to work well with systemd service management.
    
    The server uses aiosmtpd's Controller class which handles the low-level
    SMTP protocol implementation and connection management.
    """
    
    def __init__(self, handler=None, host=SMTP_HOST, port=SMTP_PORT):
        """
        Initialize SMTP server manager
        
        Args:
            handler (SMTPHandler, optional): Custom SMTP handler. If None,
                                           creates handler with configured processors.
            host (str): IP address to bind to (default from config)
            port (int): Port number to listen on (default from config)
        """
        # Create handler with processors if not provided
        if handler is None:
            processors = create_processors()
            handler = SMTPHandler(processors)
        
        self.handler = handler
        self.host = host
        self.port = port
        self.controller = None
        self.running = False
    
    def start(self):
        """
        Start the SMTP server
        
        Creates and starts the aiosmtpd Controller which handles:
        - TCP socket binding and listening
        - SMTP protocol implementation
        - Connection management and threading
        - Message routing to our handler
        
        Raises:
            OSError: If unable to bind to the specified host/port
            Exception: If server startup fails for other reasons
        """
        # Create aiosmtpd controller with our handler
        self.controller = Controller(
            self.handler,
            hostname=self.host,
            port=self.port
        )
        
        # Start the server (non-blocking)
        self.controller.start()
        self.running = True
        
        # Log startup information for monitoring
        logger.info(f"SMTP server started on {self.host}:{self.port}")
        logger.info(f"Configured processors: {len(self.handler.processors)}")
    
    def stop(self):
        """
        Stop the SMTP server gracefully
        
        Shuts down the aiosmtpd Controller which:
        - Stops accepting new connections
        - Allows existing connections to complete
        - Closes the listening socket
        - Cleans up resources
        """
        if self.controller and self.running:
            self.controller.stop()
            self.running = False
            logger.info("SMTP server stopped")
    
    async def run_forever(self):
        """
        Run server until stopped
        
        This coroutine keeps the server running by sleeping in a loop
        until the running flag is set to False. This allows the main
        event loop to handle other tasks while keeping the server alive.
        
        Used by the main() function to keep the process running until
        a shutdown signal is received.
        """
        while self.running:
            await asyncio.sleep(1)


def setup_logging():
    """
    Setup logging configuration for systemd deployment
    
    Configures Python logging to output to stdout with a structured
    format suitable for systemd/journald ingestion. The log level
    is controlled by the LOG_LEVEL environment variable.
    
    Log Format:
        timestamp - logger_name - level - message
        
    Output:
        All logs go to stdout for journald capture
    """
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format=log_format,
        stream=sys.stdout
    )


def main():
    """
    Main entry point for SMTP server
    
    Sets up logging, creates the server manager, registers signal handlers
    for graceful shutdown, and runs the server until terminated.
    
    Signal Handling:
        SIGTERM: Graceful shutdown (systemd stop)
        SIGINT: Graceful shutdown (Ctrl+C)
        
    Exit Codes:
        0: Normal shutdown
        1: Fatal error during startup or operation
    """
    # Initialize logging for systemd
    setup_logging()
    
    # Create server manager with default configuration
    server = SMTPServerManager()
    
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down...")
        server.stop()
        sys.exit(0)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)  # systemd stop
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    
    async def run_server():
        """
        Async wrapper for server execution
        
        Handles server startup, runs the main loop, and ensures
        proper cleanup on exit or error.
        """
        try:
            # Start the SMTP server
            server.start()
            logger.info("SMTP server running, waiting for connections...")
            
            # Keep server running until shutdown
            await server.run_forever()
        except Exception as e:
            # Log fatal errors and ensure cleanup
            logger.error(f"Server error: {e}")
            server.stop()
            raise
    
    try:
        # Run the async server
        asyncio.run(run_server())
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        logger.info("Received keyboard interrupt")
    except Exception as e:
        # Handle fatal errors
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        # Ensure server is stopped
        server.stop()


if __name__ == '__main__':
    import sys
    
    # Check for configuration generator flag
    if '--generate-config' in sys.argv:
        from config_generator import ConfigGenerator
        clean_output = '--clean' in sys.argv
        generator = ConfigGenerator()
        generator.run(clean_output)
    else:
        main()
