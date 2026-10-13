#!/usr/bin/env python3
"""
End-to-End Event Flow Test
Sends telemetry → Verifies forecasting → Verifies MPC decisions
"""
import json
import time
from kafka import KafkaProducer, KafkaConsumer
from datetime import datetime

KAFKA_BOOTSTRAP = 'localhost:9093'  # Host port

def send_telemetry(producer, building_id="supermarket_001"):
    """Send test telemetry event"""
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "building_id": building_id,
        "energy_consumption_kw": 150.5,
        "pv_generation_kw": 45.2,
        "battery_soc_percent": 65.0,
        "grid_price_eur_per_kwh": 0.25,
        "outdoor_temp_c": 18.5
    }
    
    producer.send('telemetry.raw', value=event)
    producer.flush()
    print(f"✓ Sent telemetry: {event['timestamp']}")
    print(f"  - Consumption: {event['energy_consumption_kw']} kW")
    print(f"  - PV: {event['pv_generation_kw']} kW")
    print(f"  - Battery SOC: {event['battery_soc_percent']}%")
    return event

def consume_predictions(timeout=10):
    """Consume forecasting predictions"""
    print(f"\nWaiting up to {timeout}s for predictions...")
    consumer = KafkaConsumer(
        'forecasting.predictions',
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset='latest',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        consumer_timeout_ms=timeout * 1000
    )
    
    predictions = []
    for message in consumer:
        predictions.append(message.value)
        print(f"✓ Received prediction:")
        pred = message.value
        if 'forecast_consumption_kw' in pred:
            print(f"  - Forecast consumption: {pred['forecast_consumption_kw']} kW")
        if 'forecast_pv_kw' in pred:
            print(f"  - Forecast PV: {pred['forecast_pv_kw']} kW")
        if 'flexibility_up_kw' in pred:
            print(f"  - Flexibility up: {pred['flexibility_up_kw']} kW")
        break  # Get first message
    
    consumer.close()
    return predictions

def consume_decisions(timeout=10):
    """Consume MPC decisions"""
    print(f"\nWaiting up to {timeout}s for MPC decisions...")
    consumer = KafkaConsumer(
        'mpc.decisions',
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset='latest',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        consumer_timeout_ms=timeout * 1000
    )
    
    decisions = []
    for message in consumer:
        decisions.append(message.value)
        print(f"✓ Received MPC decision:")
        dec = message.value
        if 'battery_charge_kw' in dec:
            print(f"  - Battery charge: {dec['battery_charge_kw']} kW")
        if 'grid_import_kw' in dec:
            print(f"  - Grid import: {dec['grid_import_kw']} kW")
        if 'total_shed_kw' in dec:
            print(f"  - Total shed: {dec['total_shed_kw']} kW")
        break  # Get first message
    
    consumer.close()
    return decisions

def main():
    print("=" * 70)
    print("SMART SUPERMARKET B2G - END-TO-END EVENT FLOW TEST")
    print("=" * 70)
    
    # Create producer
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    
    print("\n[STEP 1/3] Sending telemetry event to 'telemetry.raw' topic...")
    telemetry = send_telemetry(producer)
    
    print("\n[STEP 2/3] Waiting for Forecasting Service to process...")
    time.sleep(3)  # Give service time to process
    predictions = consume_predictions(timeout=10)
    
    if predictions:
        print(f"\n✅ FORECASTING SERVICE WORKING! Received {len(predictions)} prediction(s)")
    else:
        print("\n❌ NO PREDICTIONS RECEIVED - Check forecasting service logs:")
        print("   docker compose logs forecasting --tail=50")
        producer.close()
        return False
    
    print("\n[STEP 3/3] Waiting for MPC Service to process predictions...")
    time.sleep(3)  # Give MPC time to process
    decisions = consume_decisions(timeout=10)
    
    if decisions:
        print(f"\n✅ MPC SERVICE WORKING! Received {len(decisions)} decision(s)")
    else:
        print("\n❌ NO DECISIONS RECEIVED - Check MPC service logs:")
        print("   docker compose logs mpc --tail=50")
        producer.close()
        return False
    
    print("\n" + "=" * 70)
    print("✅✅✅ END-TO-END TEST PASSED ✅✅✅")
    print("=" * 70)
    print(f"\nEvent flow verified:")
    print(f"  telemetry.raw → Forecasting Service → forecasting.predictions")
    print(f"                → MPC Service → mpc.decisions")
    print(f"\n🎉 Microservices architecture is working correctly!")
    
    producer.close()
    return True

if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
