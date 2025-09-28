#!/usr/bin/env python3
"""
Redis worker service for processing queued emails

This module implements a worker service that reads Redis Streams for
email messages and processes them through configured processors. It's
designed to work as part of a decoupled email processing architecture
where SMTP servers queue emails and workers process them asynchronously.

Architecture:
    Redis Stream -> Worker -> Processors -> (S3 | SES | SMTP.com | File)

Key Features:
    - Redis Streams with consumer groups for reliable message processing
    - Automatic message acknowledgment on successful processing
    - Graceful error handling and logging
    - Systemd integration with signal handling
    - Email message reconstruction from Redis storage
    - Support for multiple workers with consumer groups
"""

import asyncio
import json
import logging
import signal
import sys
import os
from email.message import EmailMessage

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, rely on system environment
    pass

# Import Redis with fallback handling
try:
    import redis.asyncio as aioredis
    from redis.exceptions import ResponseError, ConnectionError as RedisConnectionError
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

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
    the envelope information from the Redis message payload.
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


class RedisWorker:
    """
    Redis worker for processing queued emails
    
    This class implements a worker that continuously reads from a Redis Stream
    for email messages, processes them through configured processors,
    and manages message lifecycle (acknowledgment on success).
    
    The worker uses Redis Streams with consumer groups to ensure reliable
    message processing and load distribution across multiple workers.
    """
    
    def __init__(self, stream_name, consumer_group='workers', consumer_name=None, 
                 processors=None, rule_engine=None, redis_config=None):
        """
        Initialize Redis worker
        
        Args:
            stream_name (str): Redis Stream name to read from
            consumer_group (str): Consumer group name for distributed processing
            consumer_name (str, optional): Unique consumer name (auto-generated if not provided)
            processors (list, optional): List of EmailProcessor instances (legacy mode)
            rule_engine (RuleEngine, optional): Rule engine for conditional routing
            redis_config (dict, optional): Redis connection configuration
            
        Raises:
            ImportError: If redis is not available
        """
        if not HAS_REDIS:
            raise ImportError("redis required for Redis worker")
        
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f'worker-{os.getpid()}'
        self.processors = processors or []
        self.rule_engine = rule_engine
        self.running = False
        
        # Redis configuration
        redis_config = redis_config or {}
        self.redis_host = redis_config.get('host', 'localhost')
        self.redis_port = redis_config.get('port', 6379)
        self.redis_db = redis_config.get('db', 0)
        self.redis_password = redis_config.get('password')
        self.redis_username = redis_config.get('username')
        self.redis_ssl = redis_config.get('ssl', False)
        
        # Initialize Redis connections
        self._connection_pool = None
        self._redis = None
        
        # Load rules if rule engine is provided
        if self.rule_engine:
            self.rule_engine.load_rules()
            logger.info("Rule-based routing enabled")
        else:
            logger.info(f"Legacy mode with {len(self.processors)} static processors")
    
    async def _get_redis(self):
        """Get Redis connection (lazy initialization)"""
        if self._redis is None:
            # Create connection pool
            self._connection_pool = aioredis.ConnectionPool(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                username=self.redis_username,
                ssl=self.redis_ssl,
                max_connections=10,
                decode_responses=True  # Decode responses for easier JSON parsing
            )
            
            # Create Redis client
            self._redis = aioredis.Redis(connection_pool=self._connection_pool)
            
            # Test connection
            try:
                await self._redis.ping()
                logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            except Exception as e:
                raise RedisConnectionError(f"Failed to connect to Redis: {e}")
        
        return self._redis
    
    def start(self):
        """
        Start the worker
        
        Initializes the worker state and logs startup information.
        The actual processing loop is started by calling run_forever().
        """
        self.running = True
        logger.info(f"Redis worker started, reading from stream: {self.stream_name}")
        logger.info(f"Consumer group: {self.consumer_group}, Consumer name: {self.consumer_name}")
        logger.info(f"Configured processors: {len(self.processors)}")
    
    def stop(self):
        """
        Stop the worker gracefully
        
        Sets the running flag to False, which will cause the reading
        loop to exit after the current iteration completes.
        """
        self.running = False
        logger.info("Redis worker stopped")
    
    async def close(self):
        """Close Redis connections"""
        if self._redis:
            await self._redis.aclose()
        if self._connection_pool:
            await self._connection_pool.aclose()
    
    async def run_forever(self):
        """
        Run worker until stopped
        
        Main worker loop that continuously reads from Redis Stream
        and processes messages. Includes error handling and backoff
        logic for resilient operation.
        
        The loop continues until self.running is set to False,
        typically by a signal handler.
        """
        redis_client = await self._get_redis()
        
        # Create consumer group if it doesn't exist
        try:
            await redis_client.xgroup_create(
                self.stream_name, 
                self.consumer_group, 
                id='0', 
                mkstream=True
            )
            logger.info(f"Created consumer group '{self.consumer_group}' for stream '{self.stream_name}'")
        except ResponseError as e:
            # Group might already exist, which is fine
            logger.debug(f"Consumer group creation result: {e}")
        except Exception as e:
            # Other connection or Redis errors
            logger.error(f"Error creating consumer group: {e}")
        
        while self.running:
            try:
                # Read messages from stream
                await self._read_messages(redis_client)
            except RedisConnectionError as e:
                # Connection errors need backoff
                logger.error(f"Redis connection error in worker loop: {e}")
                await asyncio.sleep(5)  # Backoff on connection error
            except Exception as e:
                # Log other errors and continue with shorter backoff
                logger.error(f"Error in worker loop: {e}")
                await asyncio.sleep(1)  # Shorter backoff for other errors
    
    async def _read_messages(self, redis_client):
        """
        Read messages from Redis Stream and process them
        
        Uses XREADGROUP to read messages as part of consumer group,
        ensuring reliable distributed processing across multiple workers.
        
        Args:
            redis_client: Redis client instance
        """
        try:
            # Read from stream using consumer group
            # '>' means read only new messages not delivered to other consumers
            streams = {self.stream_name: '>'}
            
            messages = await redis_client.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                streams,
                count=10,  # Batch size
                block=5000,  # 5 seconds timeout
                noack=False  # We want explicit acknowledgment
            )
            
            # Process each message
            if messages:
                stream_messages = messages[0][1]  # [(stream_name, [(msg_id, fields), ...])]
                
                for message_id, fields in stream_messages:
                    await self._process_message(redis_client, message_id, fields)
                    
        except Exception as e:
            logger.error(f"Error reading from Redis Stream: {e}")
    
    async def _process_message(self, redis_client, message_id, fields):
        """
        Process a single Redis Stream message
        
        Parses the message payload, reconstructs the email from Redis storage,
        processes through configured processors, and acknowledges the message
        on success.
        
        Args:
            redis_client: Redis client instance
            message_id: Redis Stream message ID
            fields (dict): Message fields from stream
        """
        try:
            # Extract payload from stream message
            if 'payload' not in fields:
                logger.error(f"Message {message_id} missing payload field")
                await self._ack_message(redis_client, message_id)
                return
            
            # Parse the JSON payload
            message_data = json.loads(fields['payload'])
            
            # Reconstruct email from Redis
            email_msg = await self._reconstruct_from_redis(redis_client, message_data)
            if not email_msg:
                logger.error(f"Failed to reconstruct email for message {message_id}")
                await self._ack_message(redis_client, message_id)  # Ack to prevent reprocessing
                return
            
            # Create envelope object for processor compatibility
            envelope = EmailEnvelope(
                message_data['envelope']['mail_from'],
                message_data['envelope']['rcpt_tos']
            )
            
            # Process through configured processors
            success = await self._process_email(envelope, email_msg, message_data['id'])
            
            if success:
                # Acknowledge message on successful processing
                await self._ack_message(redis_client, message_id)
                logger.info(f"Successfully processed email {message_data['id']} (stream msg: {message_id})")
            else:
                # Leave message unacknowledged for retry
                # Redis will redeliver after consumer timeout
                logger.warning(f"Failed to process email {message_data['id']} (stream msg: {message_id})")
                
        except json.JSONDecodeError as e:
            logger.error(f"Malformed JSON in message {message_id}: {e}")
            await self._ack_message(redis_client, message_id)  # Ack malformed messages
        except Exception as e:
            logger.error(f"Error processing message {message_id}: {e}")
            # Don't ack on general errors - allow retry
    
    async def _ack_message(self, redis_client, message_id):
        """
        Acknowledge a message in the consumer group
        
        Args:
            redis_client: Redis client instance
            message_id: Message ID to acknowledge
        """
        try:
            await redis_client.xack(self.stream_name, self.consumer_group, message_id)
            logger.debug(f"Acknowledged message {message_id}")
        except Exception as e:
            logger.error(f"Failed to acknowledge message {message_id}: {e}")
    
    async def _reconstruct_from_redis(self, redis_client, message_data):
        """
        Reconstruct email from Redis storage
        
        Args:
            redis_client: Redis client instance
            message_data (dict): Message data containing redis_reference
            
        Returns:
            EmailMessage: Reconstructed email message or None on failure
        """
        try:
            redis_ref = message_data['redis_reference']
            email_key = redis_ref['key']
            
            # Retrieve email data from Redis
            email_data = await redis_client.hgetall(email_key)
            if not email_data:
                logger.error(f"Email not found in Redis: {email_key}")
                return None
            
            # Parse the raw RFC822 message
            raw_message = email_data.get('raw_message')
            if not raw_message:
                logger.error(f"No raw message data in Redis key: {email_key}")
                return None
            
            from email import message_from_string
            return message_from_string(raw_message)
            
        except Exception as e:
            logger.error(f"Failed to reconstruct email from Redis: {e}")
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
            elif processor_type == 'redis_hybrid':
                from processors import RedisHybridProcessor
                processors.append(RedisHybridProcessor(processor_config))
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


def load_redis_worker_config():
    """
    Load Redis worker configuration from dot-notation environment variables
    
    Returns:
        dict: Redis configuration parameters
    """
    from config_parser import parse_dot_notation_env
    
    config = parse_dot_notation_env()
    
    # Get worker.redis configuration
    redis_config = config.get('worker', {}).get('redis', {})
    
    # Return configuration with defaults
    return {
        'stream_name': redis_config.get('stream_name'),
        'host': redis_config.get('host', 'localhost'),
        'port': int(redis_config.get('port', 6379)),
        'db': int(redis_config.get('db', 0)),
        'password': redis_config.get('password'),
        'username': redis_config.get('username'),
        'ssl': str(redis_config.get('ssl', 'false')).lower() == 'true',
        'consumer_group': redis_config.get('consumer_group', 'workers'),
        'consumer_name': redis_config.get('consumer_name')
    }


def main():
    """
    Main entry point for Redis worker
    
    Sets up logging, validates configuration, creates the worker,
    registers signal handlers, and runs the worker until terminated.
    
    Environment Variables:
        worker.redis.stream_name: Required Redis Stream name to read from
        worker.redis.host: Redis server hostname (default: localhost)
        worker.redis.port: Redis server port (default: 6379)
        worker.redis.db: Redis database number (default: 0)
        worker.redis.password: Redis authentication password (optional)
        worker.redis.username: Redis authentication username (optional)
        worker.redis.ssl: Enable SSL/TLS (default: false)
        worker.redis.consumer_group: Consumer group name (default: workers)
        worker.redis.consumer_name: Consumer name (auto-generated if not provided)
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
    
    # Load Redis worker configuration using dot notation
    redis_config = load_redis_worker_config()
    stream_name = redis_config['stream_name']
    
    if not stream_name:
        logger.error("worker.redis.stream_name configuration required")
        sys.exit(1)
    
    consumer_group = redis_config['consumer_group']
    consumer_name = redis_config['consumer_name']
    
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
        
        worker = RedisWorker(
            stream_name, consumer_group, consumer_name,
            rule_engine=rule_engine, redis_config=redis_config
        )
    else:
        # Use legacy static processors
        processors = create_worker_processors()
        worker = RedisWorker(
            stream_name, consumer_group, consumer_name,
            processors=processors, redis_config=redis_config
        )
    
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
        
        Handles worker startup, runs the main processing loop, and
        ensures proper cleanup on exit or error.
        """
        try:
            # Start the worker
            worker.start()
            
            # Run the main processing loop
            await worker.run_forever()
        except Exception as e:
            # Log fatal errors and ensure cleanup
            logger.error(f"Worker error: {e}")
            raise
        finally:
            # Ensure worker is stopped and connections closed
            worker.stop()
            await worker.close()
    
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


if __name__ == '__main__':
    main()