#!/usr/bin/env python3
"""
Integration Test for DERMS Microservice
========================================
Tests end-to-end message flow:
1. Publish test MPC decision to mpc.decisions topic
2. Wait for DERMS service to process
3. Consume from derms.dispatch topic
4. Validate output schema and physical constraints
"""

import sys
import time
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from kafka_utils.utils import create_producer, create_consumer


def test_derms_service():
    """Test DERMS service end-to-end message processing."""
    
    print("=" * 60)
    print("🧪 DERMS Service Integration Test")
    print("=" * 60)
    
    bootstrap_servers = 'localhost:9093'
    
    # Create producer and consumer
    print(f"\n1. Connecting to Kafka at {bootstrap_servers}...")
    producer = create_producer(bootstrap_servers=bootstrap_servers)
    consumer = create_consumer(
        'derms.dispatch',
        group_id='derms-test-consumer',
        bootstrap_servers=bootstrap_servers,
        auto_offset_reset='latest'  # Only read new messages
    )
    
    # Build test MPC decision
    test_timestamp = time.strftime('%Y-%m-%dT%H:%M:%S')
    test_decision = {
        'timestamp': test_timestamp,
        'peak_shave': True,
        'peak_shave_kw': 25.0,
        'load_shift_hvac': False,
        'hvac_shed_kw': 0.0,
        'valley_fill': False,
        'valley_fill_kw': 0.0,
        'hard_shed_tiers': [],
        'hard_shed_kw': 0.0,
        'active_action_names': ['peak_shaving'],
        'total_battery_request_kw': 25.0,
        'service': 'mpc'
    }
    
    print(f"\n2. Publishing test MPC decision...")
    print(f"   Timestamp: {test_timestamp}")
    print(f"   Action: Peak shaving (25.0 kW)")
    
    producer.send('mpc.decisions', test_decision)
    producer.flush()
    print("   ✓ Published to mpc.decisions")
    
    # Wait for processing
    print("\n3. Waiting for DERMS service to process (3 seconds)...")
    time.sleep(3)
    
    # Consume result
    print("\n4. Consuming from derms.dispatch...")
    dispatch = None
    timeout = time.time() + 5  # 5-second timeout
    
    for message in consumer:
        if message.value['timestamp'] == test_timestamp:
            dispatch = message.value
            print("   ✓ Received dispatch message")
            break
        if time.time() > timeout:
            print("   ✗ Timeout waiting for message")
            break
    
    # Validate output
    if dispatch is None:
        print("\n❌ TEST FAILED: No dispatch message received")
        producer.close()
        consumer.close()
        return False
    
    print("\n5. Validating dispatch message...")
    
    # Check required fields
    required_fields = [
        'timestamp', 'commands', 'total_commands',
        'battery_power', 'grid_power', 'p2p_energy',
        'shed_kw', 'battery_soc_after', 'service'
    ]
    
    missing_fields = [f for f in required_fields if f not in dispatch]
    if missing_fields:
        print(f"   ✗ Missing fields: {missing_fields}")
        producer.close()
        consumer.close()
        return False
    print("   ✓ All required fields present")
    
    # Check timestamp matches
    if dispatch['timestamp'] != test_timestamp:
        print(f"   ✗ Timestamp mismatch: {dispatch['timestamp']} != {test_timestamp}")
        producer.close()
        consumer.close()
        return False
    print("   ✓ Timestamp matches")
    
    # Check service field
    if dispatch['service'] != 'derms':
        print(f"   ✗ Service field incorrect: {dispatch['service']}")
        producer.close()
        consumer.close()
        return False
    print("   ✓ Service field correct")
    
    # Check data types
    if not isinstance(dispatch['battery_power'], (int, float)):
        print(f"   ✗ battery_power is not numeric: {type(dispatch['battery_power'])}")
        producer.close()
        consumer.close()
        return False
    
    if not isinstance(dispatch['commands'], list):
        print(f"   ✗ commands is not a list: {type(dispatch['commands'])}")
        producer.close()
        consumer.close()
        return False
    print("   ✓ Data types correct")
    
    # Check physical constraints
    battery_power = dispatch['battery_power']
    battery_soc = dispatch['battery_soc_after']
    
    if not (-50.0 <= battery_power <= 50.0):
        print(f"   ✗ Battery power out of bounds: {battery_power} kW (limit: ±50 kW)")
        producer.close()
        consumer.close()
        return False
    
    if not (10.0 <= battery_soc <= 95.0):
        print(f"   ✗ Battery SOC out of bounds: {battery_soc}% (limit: 10-95%)")
        producer.close()
        consumer.close()
        return False
    print("   ✓ Physical constraints satisfied")
    
    # Check commands structure
    if dispatch['total_commands'] != len(dispatch['commands']):
        print(f"   ✗ Command count mismatch: {dispatch['total_commands']} != {len(dispatch['commands'])}")
        producer.close()
        consumer.close()
        return False
    
    for i, cmd in enumerate(dispatch['commands']):
        required_cmd_fields = ['equipment_id', 'command_type', 'duration_min']
        missing_cmd_fields = [f for f in required_cmd_fields if f not in cmd]
        if missing_cmd_fields:
            print(f"   ✗ Command {i} missing fields: {missing_cmd_fields}")
            producer.close()
            consumer.close()
            return False
    print(f"   ✓ {len(dispatch['commands'])} commands properly structured")
    
    # Print summary
    print("\n6. Dispatch Summary:")
    print(f"   Commands: {dispatch['total_commands']}")
    print(f"   Battery Power: {battery_power:.1f} kW ({'discharge' if battery_power > 0 else 'charge'})")
    print(f"   Grid Power: {dispatch['grid_power']:.1f} kW")
    print(f"   Shed Power: {dispatch['shed_kw']:.1f} kW")
    print(f"   Battery SOC After: {battery_soc:.1f}%")
    print("\n   Equipment Commands:")
    for cmd in dispatch['commands']:
        if 'setpoint_kw' in cmd:
            print(f"   - {cmd['equipment_id']}: {cmd['command_type']} @ {cmd['setpoint_kw']:.1f} kW for {cmd['duration_min']} min")
        elif 'setpoint_percent' in cmd:
            print(f"   - {cmd['equipment_id']}: {cmd['command_type']} @ {cmd['setpoint_percent']}% for {cmd['duration_min']} min")
    
    # Cleanup
    producer.close()
    consumer.close()
    
    print("\n" + "=" * 60)
    print("🎉 DERMS Service Test PASSED")
    print("=" * 60)
    print("✓ Message published to mpc.decisions")
    print("✓ DERMS consumed and processed message")
    print("✓ Dispatch published to derms.dispatch")
    print("✓ All required fields present")
    print("✓ Physical constraints satisfied")
    print("=" * 60)
    
    return True


if __name__ == '__main__':
    try:
        success = test_derms_service()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
