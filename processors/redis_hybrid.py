#!/usr/bin/env python3
"""
Hybrid Redis processor for handling emails of any size
"""

import json
import uuid
from datetime import datetime
from email.message import EmailMessage
from .base import EmailProcessor

try:
    import redis.asyncio as aioredis
    from redis.exceptions import ResponseError, ConnectionError as RedisConnectionError
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


class RedisHybridProcessor(EmailProcessor):
    """Store emails in Redis and queue metadata in Redis Streams"""
    
    def __init__(self, config=None):
        super().__init__(config)
        if not HAS_REDIS:
            raise ImportError("redis required for RedisHybridProcessor")
        
        self.redis_host = self.config.get('redis_host', 'localhost')
        self.redis_port = self.config.get('redis_port', 6379)
        self.redis_db = self.config.get('redis_db', 0)
        self.redis_password = self.config.get('redis_password')
        self.redis_username = self.config.get('redis_username')
        self.redis_ssl = self.config.get('redis_ssl', False)
        
        self.stream_name = self.config.get('stream_name', 'email_queue')
        self.email_ttl = self.config.get('email_ttl', 86400)  # 24 hours default
        self.key_prefix = self.config.get('key_prefix', 'email:')
        
        if not self.stream_name:
            raise ValueError("stream_name required for Redis processor")
        
        # Initialize async Redis connection pool
        self._connection_pool = None
        self._redis = None
    
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
                decode_responses=True  # Use string responses for easier handling
            )
            
            # Create Redis client
            self._redis = aioredis.Redis(connection_pool=self._connection_pool)
            
            # Test connection
            try:
                await self._redis.ping()
            except Exception as e:
                raise RedisConnectionError(f"Failed to connect to Redis: {e}")
        
        return self._redis
    
    async def process(self, envelope, message: EmailMessage) -> bool:
        """Store email in Redis and queue metadata in Redis Stream"""
        try:
            redis_client = await self._get_redis()
            message_id = str(uuid.uuid4())
            timestamp = datetime.utcnow()
            
            # Generate Redis keys
            email_key = f"{self.key_prefix}{message_id}"
            
            # Store complete email in Redis with TTL
            email_success = await self._store_email_in_redis(
                redis_client, email_key, message, message_id
            )
            if not email_success:
                return False
            
            # Create lightweight stream message with metadata and Redis reference
            stream_message = {
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
                'redis_reference': {
                    'key': email_key,
                    'host': self.redis_host,
                    'port': self.redis_port,
                    'db': self.redis_db
                }
            }
            
            # Add message to Redis Stream
            # Using XADD with auto-generated ID
            stream_fields = {
                'message_id': message_id,
                'payload': json.dumps(stream_message),
                'from_domain': self._extract_domain(envelope.mail_from),
                'to_domain': self._extract_domain(envelope.rcpt_tos[0] if envelope.rcpt_tos else ''),
                'has_attachments': str(stream_message['metadata']['has_attachments']).lower(),
                'size_bytes': str(stream_message['metadata']['size_bytes'])
            }
            
            stream_id = await redis_client.xadd(self.stream_name, stream_fields)
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Email {message_id} stored in Redis and queued with stream ID: {stream_id}")
            
            return True
            
        except Exception as e:
            # Log detailed error information for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Redis Hybrid processor failed: {e}")
            logger.error(f"Redis host: {self.redis_host}:{self.redis_port}")
            logger.error(f"Stream name: {self.stream_name}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def _store_email_in_redis(self, redis_client, email_key, message, message_id):
        """Store complete email in Redis with metadata"""
        try:
            email_data = {
                'message_id': message_id,
                'raw_message': message.as_string(),
                'subject': message.get('Subject', '')[:1000],  # Truncate for efficiency
                'from': message.get('From', '')[:1000],
                'to': message.get('To', '')[:1000],
                'date': message.get('Date', ''),
                'content_type': message.get_content_type(),
                'has_attachments': str(self._has_attachments(message)),
                'is_multipart': str(message.is_multipart()),
                'size_bytes': str(len(str(message))),
                'stored_at': datetime.utcnow().isoformat()
            }
            
            # Use pipeline for atomic operation
            pipe = redis_client.pipeline()
            pipe.hset(email_key, mapping=email_data)
            if self.email_ttl > 0:
                pipe.expire(email_key, self.email_ttl)
            await pipe.execute()
            
            return True
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to store email in Redis: {e}")
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
    
    async def close(self):
        """Close Redis connections"""
        if self._redis:
            await self._redis.aclose()
        if self._connection_pool:
            await self._connection_pool.aclose()
    
    def get_name(self) -> str:
        return "RedisHybrid"
    
    @classmethod
    def get_config_spec(cls):
        """Get configuration specification for this processor"""
        return {
            'redis_host': {
                'type': 'string',
                'required': False,
                'default': 'localhost',
                'description': 'Redis server hostname or IP address'
            },
            'redis_port': {
                'type': 'int', 
                'required': False,
                'default': 6379,
                'description': 'Redis server port'
            },
            'redis_db': {
                'type': 'int',
                'required': False,
                'default': 0,
                'description': 'Redis database number'
            },
            'redis_password': {
                'type': 'string',
                'required': False,
                'description': 'Redis authentication password'
            },
            'redis_username': {
                'type': 'string',
                'required': False,
                'description': 'Redis authentication username (Redis 6.0+)'
            },
            'redis_ssl': {
                'type': 'bool',
                'required': False,
                'default': False,
                'description': 'Enable SSL/TLS connection to Redis'
            },
            'stream_name': {
                'type': 'string',
                'required': False,
                'default': 'email_queue',
                'description': 'Redis Stream name for email queue'
            },
            'email_ttl': {
                'type': 'int',
                'required': False,
                'default': 86400,
                'description': 'Email storage TTL in seconds (0 for no expiration)'
            },
            'key_prefix': {
                'type': 'string',
                'required': False,
                'default': 'email:',
                'description': 'Prefix for Redis keys storing emails'
            }
        }