"""
Kafka Producer/Consumer Utilities for B2G Microservices
=========================================================
Provides reusable Kafka client creation with standardized configuration
for use across all microservices.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


def get_bootstrap_servers() -> str:
    """Get Kafka bootstrap servers from environment or default."""
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093")


def create_producer(
    bootstrap_servers: str | None = None,
    **kwargs: Any
) -> KafkaProducer:
    """
    Create a Kafka producer with standardized configuration.
    
    Parameters
    ----------
    bootstrap_servers : str, optional
        Kafka broker addresses. Defaults to environment variable or localhost:9093
    **kwargs
        Additional KafkaProducer arguments
    
    Returns
    -------
    KafkaProducer
        Configured producer instance
    
    Example
    -------
    >>> producer = create_producer()
    >>> producer.send('telemetry.raw', {'timestamp': '2025-06-01', 'pv_power': 15.4})
    >>> producer.flush()
    """
    if bootstrap_servers is None:
        bootstrap_servers = get_bootstrap_servers()
    
    default_config = {
        'bootstrap_servers': bootstrap_servers,
        'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
        'key_serializer': lambda k: k.encode('utf-8') if k else None,
        'acks': 'all',  # Wait for all replicas to acknowledge
        'retries': 3,
        'max_in_flight_requests_per_connection': 1,  # Guarantee ordering
        'compression_type': 'lz4',  # Efficient compression
        'linger_ms': 10,  # Small batching for better throughput
    }
    
    # Override with user-provided kwargs
    default_config.update(kwargs)
    
    logger.info(f"Creating Kafka producer connecting to {bootstrap_servers}")
    try:
        producer = KafkaProducer(**default_config)
        logger.info("Kafka producer created successfully")
        return producer
    except KafkaError as e:
        logger.error(f"Failed to create Kafka producer: {e}")
        raise


def create_consumer(
    *topics: str,
    group_id: str,
    bootstrap_servers: str | None = None,
    **kwargs: Any
) -> KafkaConsumer:
    """
    Create a Kafka consumer with standardized configuration.
    
    Parameters
    ----------
    *topics : str
        One or more topic names to subscribe to
    group_id : str
        Consumer group identifier
    bootstrap_servers : str, optional
        Kafka broker addresses
    **kwargs
        Additional KafkaConsumer arguments
    
    Returns
    -------
    KafkaConsumer
        Configured consumer instance
    
    Example
    -------
    >>> consumer = create_consumer('telemetry.raw', group_id='forecasting-service')
    >>> for message in consumer:
    ...     process(message.value)
    """
    if bootstrap_servers is None:
        bootstrap_servers = get_bootstrap_servers()
    
    default_config = {
        'bootstrap_servers': bootstrap_servers,
        'group_id': group_id,
        'value_deserializer': lambda v: json.loads(v.decode('utf-8')),
        'key_deserializer': lambda k: k.decode('utf-8') if k else None,
        'auto_offset_reset': 'earliest',  # Read from beginning if no offset
        'enable_auto_commit': True,
        'auto_commit_interval_ms': 1000,
        'max_poll_records': 100,
        'session_timeout_ms': 30000,
        'heartbeat_interval_ms': 10000,
    }
    
    # Override with user-provided kwargs
    default_config.update(kwargs)
    
    logger.info(f"Creating Kafka consumer for topics {topics}, group={group_id}")
    try:
        consumer = KafkaConsumer(*topics, **default_config)
        logger.info(f"Kafka consumer created successfully, subscribed to: {topics}")
        return consumer
    except KafkaError as e:
        logger.error(f"Failed to create Kafka consumer: {e}")
        raise


def send_message(
    producer: KafkaProducer,
    topic: str,
    value: dict,
    key: str | None = None,
    on_success: Callable | None = None,
    on_error: Callable | None = None,
) -> None:
    """
    Send a message to Kafka with error handling.
    
    Parameters
    ----------
    producer : KafkaProducer
        Producer instance
    topic : str
        Target topic name
    value : dict
        Message payload (will be JSON-serialized)
    key : str, optional
        Message key for partitioning
    on_success : callable, optional
        Callback for successful send
    on_error : callable, optional
        Callback for failed send
    
    Example
    -------
    >>> producer = create_producer()
    >>> send_message(producer, 'telemetry.raw', {'temp': 22.3})
    """
    def default_success(metadata):
        logger.debug(f"Message sent to {metadata.topic}[{metadata.partition}] @ offset {metadata.offset}")
    
    def default_error(exc):
        logger.error(f"Failed to send message to {topic}: {exc}")
    
    future = producer.send(topic, key=key, value=value)
    future.add_callback(on_success or default_success)
    future.add_errback(on_error or default_error)


class MessageProcessor:
    """
    Base class for Kafka message processors in microservices.
    
    Provides standard consumer loop with error handling and graceful shutdown.
    
    Example
    -------
    class ForecastingProcessor(MessageProcessor):
        def process_message(self, message):
            telemetry = message.value
            forecast = self.forecaster.predict(telemetry)
            self.send_message('forecasting.predictions', forecast)
    """
    
    def __init__(
        self,
        input_topics: list[str],
        output_topic: str | None,
        group_id: str,
        bootstrap_servers: str | None = None
    ):
        self.consumer = create_consumer(
            *input_topics,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers
        )
        self.producer = create_producer(bootstrap_servers=bootstrap_servers) if output_topic else None
        self.output_topic = output_topic
        self.running = False
        logger.info(f"MessageProcessor initialized: {input_topics} → {output_topic}")
    
    def process_message(self, message: Any) -> dict | None:
        """
        Process a single message. Override in subclasses.
        
        Parameters
        ----------
        message : kafka.consumer.fetched.ConsumerRecord
            Kafka message
        
        Returns
        -------
        dict or None
            Output message to send to output_topic, or None to skip
        """
        raise NotImplementedError("Subclasses must implement process_message()")
    
    def run(self) -> None:
        """Start the message processing loop."""
        self.running = True
        logger.info("Starting message processor loop")
        
        try:
            for message in self.consumer:
                if not self.running:
                    break
                
                try:
                    # Process message
                    output = self.process_message(message)
                    
                    # Send to output topic if present
                    if output and self.producer and self.output_topic:
                        send_message(self.producer, self.output_topic, output)
                        self.producer.flush()
                
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    # Continue processing next message
        
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Clean shutdown of consumer and producer."""
        logger.info("Shutting down message processor")
        self.running = False
        
        if self.consumer:
            self.consumer.close()
            logger.info("Consumer closed")
        
        if self.producer:
            self.producer.flush()
            self.producer.close()
            logger.info("Producer closed")


# Health check utility
def check_kafka_health(bootstrap_servers: str | None = None) -> bool:
    """
    Check if Kafka cluster is reachable.
    
    Returns
    -------
    bool
        True if Kafka is healthy, False otherwise
    """
    if bootstrap_servers is None:
        bootstrap_servers = get_bootstrap_servers()
    
    try:
        # Try to create a producer (will fail if Kafka unreachable)
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            request_timeout_ms=5000,
            api_version_auto_timeout_ms=5000
        )
        producer.close()
        logger.info("Kafka health check: OK")
        return True
    except Exception as e:
        logger.error(f"Kafka health check failed: {e}")
        return False
