#!/usr/bin/env python3
"""
MPC Service Integration Test
=============================
Tests end-to-end message flow: publish prediction → MPC processes → consume decision.

This test requires a running Kafka broker (localhost:9093 by default).
Run with: python services/mpc/test_service.py
"""

import sys
import json
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from kafka_utils.utils import create_producer, create_consumer


def test_mpc_service():
    """Test MPC service by publishing a prediction and consuming the decision."""
    
    print("=" * 60)
    print("🧪 MPC Service Integration Test")
    print("=" * 60)
    
    bootstrap_servers = 'localhost:9093'
    
    # Create Kafka clients
    print("\n1. Connecting to Kafka...")
    try:
        producer = create_producer(bootstrap_servers=bootstrap_servers)
        consumer = create_consumer(
            'mpc.decisions',
            group_id='mpc-test-consumer',
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset='latest'  # Only read new messages
        )
        print("   ✓ Connected to Kafka")
    except Exception as e:
        print(f"   ✗ Failed to connect to Kafka: {e}")
        print("\n   Make sure Kafka is running:")
        print("   docker compose up -d kafka")
        return False
    
    # Publish test prediction
    print("\n2. Publishing test prediction to forecasting.predictions...")
    test_prediction = {
        'timestamp': '2025-06-01 12:00:00',
        'forecast_consumption': 150.5,
        'forecast_pv': 45.2,
        'anomaly_score': 0.1,
        'anomaly_flag': False,
        'anomaly_source': None,
        'flexibility_budgets': {
            'hvac_soft_shed_kw': 12.5,
            'lighting_shed_kw': 8.3,
            'checkout_shed_kw': 2.1,
            'other_shed_kw': 5.4
        },
        'telemetry': {
            'hvac_power': 25.0,
            'lighting_power': 16.6,
            'checkout_power': 42.0,
            'other_appliance_power': 10.8
        }
    }
    
    try:
        producer.send('forecasting.predictions', value=test_prediction)
        producer.flush()
        print("   ✓ Published prediction")
        print(f"      Timestamp: {test_prediction['timestamp']}")
        print(f"      Forecast consumption: {test_prediction['forecast_consumption']} kW")
        print(f"      Forecast PV: {test_prediction['forecast_pv']} kW")
    except Exception as e:
        print(f"   ✗ Failed to publish: {e}")
        producer.close()
        consumer.close()
        return False
    
    # Wait for MPC service to process
    print("\n3. Waiting for MPC service to process (3 seconds)...")
    time.sleep(3)
    
    # Consume decision
    print("\n4. Consuming MPC decision from mpc.decisions...")
    decision = None
    timeout = 5
    start_time = time.time()
    
    try:
        for message in consumer:
            decision = message.value
            print("   ✓ Received decision")
            print(f"      Timestamp: {decision.get('timestamp')}")
            print(f"      Active actions: {decision.get('active_action_names', [])}")
            print(f"      Battery request: {decision.get('total_battery_request_kw', 0):.1f} kW")
            break
        
        if decision is None:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                print(f"   ✗ No decision received within {timeout} seconds")
                print("\n   Troubleshooting:")
                print("   - Is MPC service running? docker compose ps mpc")
                print("   - Check MPC logs: docker compose logs mpc")
                producer.close()
                consumer.close()
                return False
    
    except Exception as e:
        print(f"   ✗ Failed to consume decision: {e}")
        producer.close()
        consumer.close()
        return False
    
    # Validate decision structure
    print("\n5. Validating decision structure...")
    required_fields = [
        'timestamp',
        'peak_shave',
        'peak_shave_kw',
        'load_shift_hvac',
        'hvac_shed_kw',
        'valley_fill',
        'valley_fill_kw',
        'hard_shed_tiers',
        'hard_shed_kw',
        'active_action_names',
        'total_battery_request_kw',
        'service'
    ]
    
    missing_fields = [f for f in required_fields if f not in decision]
    if missing_fields:
        print(f"   ✗ Missing fields: {missing_fields}")
        producer.close()
        consumer.close()
        return False
    
    print("   ✓ All required fields present")
    
    # Validate data types
    print("\n6. Validating data types...")
    validations = [
        (decision['timestamp'] == test_prediction['timestamp'], "Timestamp matches"),
        (isinstance(decision['peak_shave'], bool), "peak_shave is bool"),
        (isinstance(decision['peak_shave_kw'], (int, float)), "peak_shave_kw is numeric"),
        (isinstance(decision['load_shift_hvac'], bool), "load_shift_hvac is bool"),
        (isinstance(decision['hvac_shed_kw'], (int, float)), "hvac_shed_kw is numeric"),
        (isinstance(decision['valley_fill'], bool), "valley_fill is bool"),
        (isinstance(decision['valley_fill_kw'], (int, float)), "valley_fill_kw is numeric"),
        (isinstance(decision['hard_shed_tiers'], list), "hard_shed_tiers is list"),
        (isinstance(decision['hard_shed_kw'], (int, float)), "hard_shed_kw is numeric"),
        (isinstance(decision['active_action_names'], list), "active_action_names is list"),
        (isinstance(decision['total_battery_request_kw'], (int, float)), "total_battery_request_kw is numeric"),
        (decision['service'] == 'mpc', "service field is 'mpc'"),
    ]
    
    all_valid = True
    for is_valid, description in validations:
        if is_valid:
            print(f"   ✓ {description}")
        else:
            print(f"   ✗ {description}")
            all_valid = False
    
    # Cleanup
    producer.close()
    consumer.close()
    
    # Final result
    print("\n" + "=" * 60)
    if all_valid:
        print("🎉 MPC Service Test PASSED")
        print("=" * 60)
        return True
    else:
        print("❌ MPC Service Test FAILED")
        print("=" * 60)
        return False


if __name__ == '__main__':
    success = test_mpc_service()
    sys.exit(0 if success else 1)
