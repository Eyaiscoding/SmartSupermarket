#!/usr/bin/env python3
"""
Forecasting Service Integration Test
=====================================
Tests the forecasting service end-to-end:
1. Publish test telemetry to telemetry.raw
2. Verify forecasting service consumes it
3. Verify prediction is published to forecasting.predictions
4. Validate prediction format and content
"""

import sys
import time
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from kafka.utils import create_producer, create_consumer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_forecasting_service():
    """Test end-to-end flow through forecasting service."""
    
    logger.info("=" * 60)
    logger.info("🧪 Testing Forecasting Service")
    logger.info("=" * 60)
    logger.info("")
    
    # Test telemetry event
    test_telemetry = {
        'timestamp': '2025-06-01T00:00:00',
        'occupancy': 45,
        'temperature': 22.3,
        'humidity': 45.5,
        'solar_irradiance': 800.0,
        'pv_voltage': 240.0,
        'pv_current': 8.5,
        'pv_power': 15.4,
        'total_consumption': 78.2,
        'display_freezer_power': 12.3,
        'display_refrigerator_power': 8.5,
        'cold_room_power': 15.2,
        'freezer_room_power': 18.7,
        'hvac_power': 25.4,
        'lighting_power': 12.8,
        'checkout_power': 8.4,
        'it_power': 6.2,
        'other_appliance_power': 5.3,
        'battery_voltage': 48.0,
        'battery_current': -5.2,
        'battery_capacity': 100.0,
        'battery_soc': 62.3,
        'battery_power': -8.5,
        'grid_power': 23.4,
        'energy_price': 0.23,
        'demand_response': 0,
        'p2p_energy': 0.0,
        'forecast_consumption': 82.1,
        'forecast_pv': 18.3,
        'anomaly_score': 0.12,
    }
    
    try:
        # Step 1: Publish telemetry
        logger.info("Step 1: Publishing test telemetry to telemetry.raw")
        producer = create_producer(bootstrap_servers='localhost:9093')
        producer.send('telemetry.raw', value=test_telemetry)
        producer.flush()
        logger.info(f"✅ Published telemetry for timestamp: {test_telemetry['timestamp']}")
        logger.info("")
        
        # Step 2: Wait for processing
        logger.info("Step 2: Waiting for forecasting service to process...")
        time.sleep(3)
        logger.info("")
        
        # Step 3: Consume prediction
        logger.info("Step 3: Consuming prediction from forecasting.predictions")
        consumer = create_consumer(
            'forecasting.predictions',
            group_id='test-forecasting-consumer',
            bootstrap_servers='localhost:9093',
            auto_offset_reset='latest'  # Only read new messages
        )
        
        # Wait for prediction (with timeout)
        prediction_received = False
        start_time = time.time()
        timeout = 10
        
        for message in consumer:
            prediction = message.value
            logger.info(f"✅ Received prediction: {prediction}")
            logger.info("")
            
            # Step 4: Validate prediction format
            logger.info("Step 4: Validating prediction format")
            
            required_fields = [
                'timestamp',
                'forecast_consumption',
                'forecast_pv',
                'anomaly_score',
                'anomaly_flag',
                'flexibility_budgets'
            ]
            
            missing = [f for f in required_fields if f not in prediction]
            if missing:
                logger.error(f"❌ Missing required fields: {missing}")
                return False
            
            logger.info("✅ All required fields present")
            
            # Validate timestamp matches
            if prediction['timestamp'] != test_telemetry['timestamp']:
                logger.error(f"❌ Timestamp mismatch: expected {test_telemetry['timestamp']}, "
                           f"got {prediction['timestamp']}")
                return False
            
            logger.info("✅ Timestamp matches")
            
            # Validate data types
            if not isinstance(prediction['forecast_consumption'], (int, float)):
                logger.error(f"❌ forecast_consumption must be numeric, got {type(prediction['forecast_consumption'])}")
                return False
            
            if not isinstance(prediction['forecast_pv'], (int, float)):
                logger.error(f"❌ forecast_pv must be numeric, got {type(prediction['forecast_pv'])}")
                return False
            
            if not isinstance(prediction['anomaly_flag'], bool):
                logger.error(f"❌ anomaly_flag must be boolean, got {type(prediction['anomaly_flag'])}")
                return False
            
            if not isinstance(prediction['flexibility_budgets'], dict):
                logger.error(f"❌ flexibility_budgets must be dict, got {type(prediction['flexibility_budgets'])}")
                return False
            
            logger.info("✅ Data types valid")
            logger.info("")
            
            # Success!
            logger.info("=" * 60)
            logger.info("🎉 Forecasting Service Test PASSED")
            logger.info("=" * 60)
            logger.info("")
            logger.info("Prediction Summary:")
            logger.info(f"  Forecast Consumption: {prediction['forecast_consumption']:.1f} kW")
            logger.info(f"  Forecast PV: {prediction['forecast_pv']:.1f} kW")
            logger.info(f"  Anomaly Detected: {prediction['anomaly_flag']}")
            logger.info(f"  Flexibility Budgets: {prediction['flexibility_budgets']}")
            
            prediction_received = True
            break
            
            if time.time() - start_time > timeout:
                logger.error(f"❌ Timeout waiting for prediction after {timeout}s")
                break
        
        # Cleanup
        consumer.close()
        producer.close()
        
        return prediction_received
    
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}", exc_info=True)
        return False


def main():
    """Run the integration test."""
    success = test_forecasting_service()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
