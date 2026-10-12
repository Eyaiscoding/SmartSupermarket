#!/usr/bin/env python3
"""
Kafka Integration Test Script
==============================
Verifies Kafka setup by:
1. Checking Kafka connectivity
2. Creating test topics
3. Publishing test messages
4. Consuming messages back
5. Validating end-to-end flow
"""

import sys
import time
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from kafka.utils import (
    create_producer,
    create_consumer,
    send_message,
    check_kafka_health
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_kafka_health():
    """Test 1: Check Kafka is reachable."""
    logger.info("🔍 Test 1: Checking Kafka health...")
    
    if check_kafka_health():
        logger.info("✅ Kafka health check passed")
        return True
    else:
        logger.error("❌ Kafka health check failed")
        return False


def test_produce_consume():
    """Test 2: Produce and consume a test message."""
    logger.info("🔍 Test 2: Testing produce/consume flow...")
    
    test_topic = "test.messages"
    test_data = {
        "timestamp": "2025-06-01T00:00:00",
        "test_value": 42.0,
        "message": "Hello from B2G test script!"
    }
    
    try:
        # Create producer
        logger.info(f"Creating producer for topic: {test_topic}")
        producer = create_producer()
        
        # Send message
        logger.info(f"Sending test message: {test_data}")
        send_message(producer, test_topic, test_data)
        producer.flush()
        logger.info("✅ Message sent successfully")
        
        # Wait for message to be available
        time.sleep(2)
        
        # Create consumer
        logger.info(f"Creating consumer for topic: {test_topic}")
        consumer = create_consumer(
            test_topic,
            group_id="test-consumer-group",
            auto_offset_reset="earliest"
        )
        
        # Consume message (with timeout)
        logger.info("Waiting for message...")
        received = False
        start_time = time.time()
        timeout = 10  # seconds
        
        for message in consumer:
            logger.info(f"✅ Received message: {message.value}")
            
            # Validate message content
            if message.value == test_data:
                logger.info("✅ Message content matches!")
                received = True
                break
            else:
                logger.warning(f"⚠️  Message mismatch: expected {test_data}, got {message.value}")
            
            if time.time() - start_time > timeout:
                logger.error(f"❌ Timeout waiting for message after {timeout}s")
                break
        
        # Cleanup
        consumer.close()
        producer.close()
        
        return received
    
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}", exc_info=True)
        return False


def test_all_topics():
    """Test 3: Verify all B2G topics exist."""
    logger.info("🔍 Test 3: Checking B2G topics...")
    
    expected_topics = [
        "telemetry.raw",
        "forecasting.predictions",
        "mpc.decisions",
        "derms.dispatch",
        "compliance.reports"
    ]
    
    try:
        from kafka.admin import KafkaAdminClient
        
        admin = KafkaAdminClient(
            bootstrap_servers="localhost:9093",
            request_timeout_ms=5000
        )
        
        existing_topics = admin.list_topics()
        admin.close()
        
        missing = [t for t in expected_topics if t not in existing_topics]
        
        if missing:
            logger.warning(f"⚠️  Missing topics: {missing}")
            logger.info("Run: docker compose exec kafka bash /kafka/create-topics.sh")
            return False
        else:
            logger.info(f"✅ All {len(expected_topics)} topics exist")
            return True
    
    except Exception as e:
        logger.error(f"❌ Failed to check topics: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("🚀 Starting Kafka Integration Tests")
    logger.info("=" * 60)
    logger.info("")
    
    results = []
    
    # Test 1: Health check
    results.append(("Health Check", test_kafka_health()))
    logger.info("")
    
    # Test 2: Produce/Consume
    results.append(("Produce/Consume", test_produce_consume()))
    logger.info("")
    
    # Test 3: Topic verification
    results.append(("Topic Verification", test_all_topics()))
    logger.info("")
    
    # Summary
    logger.info("=" * 60)
    logger.info("📊 Test Results Summary")
    logger.info("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} - {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    logger.info("")
    logger.info(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed!")
        return 0
    else:
        logger.error(f"❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
