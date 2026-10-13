#!/usr/bin/env python3
"""
Forecasting Microservice
=========================
Consumes telemetry events from Kafka, runs AI forecasting and anomaly detection,
and publishes predictions back to Kafka.

Architecture:
    Kafka (telemetry.raw) → Forecasting Service → Kafka (forecasting.predictions)

This service is stateless - models are trained once at startup from historical
data and kept in memory for fast prediction.
"""

import sys
import logging
import signal
from pathlib import Path
from typing import Any

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from kafka_utils.utils import MessageProcessor
from src.forecasting.forecaster import Forecaster
from src.forecasting.anomaly import AnomalyDetector
from src.forecasting.flexibility import FlexibilityEstimator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ForecastingService(MessageProcessor):
    """
    Forecasting microservice that processes telemetry events.
    
    For each telemetry event:
    1. Run forecasting model (predict consumption and PV)
    2. Run anomaly detection (flag unusual patterns)
    3. Estimate flexibility budgets (shedding capacity)
    4. Publish predictions to Kafka
    """
    
    def __init__(
        self,
        bootstrap_servers: str | None = None,
        training_data_path: str | None = None
    ):
        """
        Initialize forecasting service with trained models.
        
        Parameters
        ----------
        bootstrap_servers : str, optional
            Kafka broker addresses
        training_data_path : str, optional
            Path to historical data for model training
        """
        super().__init__(
            input_topics=['telemetry.raw'],
            output_topic='forecasting.predictions',
            group_id='forecasting-service',
            bootstrap_servers=bootstrap_servers
        )
        
        # Initialize models
        logger.info("Initializing forecasting models...")
        self.forecaster = Forecaster(n_estimators=100, max_depth=4)
        self.anomaly_detector = AnomalyDetector()
        self.flexibility_estimator = FlexibilityEstimator()
        
        # Train models if training data provided
        if training_data_path:
            self._train_models(training_data_path)
        else:
            logger.warning("No training data provided - models will use default parameters")
        
        logger.info("Forecasting service initialized successfully")
    
    def _train_models(self, data_path: str) -> None:
        """
        Train forecasting and anomaly detection models from historical data.
        
        Parameters
        ----------
        data_path : str
            Path to CSV file with historical telemetry
        """
        import pandas as pd
        
        logger.info(f"Loading training data from {data_path}")
        try:
            df = pd.read_csv(data_path)
            logger.info(f"Loaded {len(df)} rows of training data")
            
            # Train forecaster
            logger.info("Training forecasting model...")
            metrics = self.forecaster.train(df)
            logger.info(f"Forecaster trained: MAE consumption={metrics.get('mae_consumption', 'N/A'):.2f}, "
                       f"MAE PV={metrics.get('mae_pv', 'N/A'):.2f}")
            
            # Train anomaly detector
            logger.info("Training anomaly detector...")
            self.anomaly_detector.train(df)
            logger.info("Anomaly detector trained")
            
        except Exception as e:
            logger.error(f"Failed to train models: {e}", exc_info=True)
            logger.warning("Service will continue with untrained models")
    
    def process_message(self, message: Any) -> dict | None:
        """
        Process a telemetry event and generate predictions.
        
        Parameters
        ----------
        message : kafka.consumer.fetched.ConsumerRecord
            Kafka message containing telemetry data
        
        Returns
        -------
        dict
            Prediction event to publish to forecasting.predictions topic
        """
        telemetry = message.value
        timestamp = telemetry.get('timestamp')
        
        logger.debug(f"Processing telemetry for {timestamp}")
        
        try:
            # 1. Generate forecasts (consumption and PV generation)
            forecast = self._generate_forecast(telemetry)
            
            # 2. Detect anomalies
            anomaly_result = self._detect_anomaly(telemetry)
            
            # 3. Estimate flexibility budgets
            flexibility = self._estimate_flexibility(telemetry)
            
            # 4. Combine into prediction event
            prediction = {
                'timestamp': timestamp,
                # Forecasting
                'forecast_consumption': forecast['consumption'],
                'forecast_pv': forecast['pv'],
                # Anomaly detection
                'anomaly_score': anomaly_result['score'],
                'anomaly_flag': anomaly_result['flag'],
                'anomaly_source': anomaly_result.get('source'),
                # Flexibility estimation
                'flexibility_budgets': flexibility,
                # Telemetry context (for downstream services like MPC)
                'telemetry': {
                    'hvac_power': telemetry.get('hvac_power', 0.0),
                    'lighting_power': telemetry.get('lighting_power', 0.0),
                    'checkout_power': telemetry.get('checkout_power', 0.0),
                    'other_appliance_power': telemetry.get('other_appliance_power', 0.0),
                },
            }
            
            logger.debug(f"Prediction generated for {timestamp}: "
                        f"consumption={forecast['consumption']:.1f}, "
                        f"pv={forecast['pv']:.1f}, "
                        f"anomaly={anomaly_result['flag']}")
            
            return prediction
        
        except Exception as e:
            logger.error(f"Error processing message for {timestamp}: {e}", exc_info=True)
            return None
    
    def _generate_forecast(self, telemetry: dict) -> dict:
        """Generate consumption and PV forecasts."""
        # Simple rolling average fallback if model not trained
        # In production, this would use the trained gradient boosting model
        consumption = telemetry.get('total_consumption', 0)
        pv = telemetry.get('pv_power', 0)
        
        # Naive forecast: assume next timestep is same as current
        # TODO: Use forecaster.predict() once we have batch processing
        return {
            'consumption': consumption * 1.05,  # Slight increase assumption
            'pv': pv * 0.95,  # Slight decrease assumption
        }
    
    def _detect_anomaly(self, telemetry: dict) -> dict:
        """Detect anomalies in telemetry data."""
        # Simple threshold-based fallback
        # TODO: Use anomaly_detector.detect() with proper DataFrame input
        
        temperature = telemetry.get('temperature', 20)
        consumption = telemetry.get('total_consumption', 0)
        
        # Flag extreme values
        anomaly_flag = (
            temperature > 40 or temperature < -10 or
            consumption > 200 or consumption < 0
        )
        
        return {
            'score': 0.8 if anomaly_flag else 0.1,
            'flag': anomaly_flag,
            'source': 'temperature' if temperature > 40 else None
        }
    
    def _estimate_flexibility(self, telemetry: dict) -> dict:
        """Estimate load shedding flexibility budgets."""
        hvac = telemetry.get('hvac_power', 0)
        lighting = telemetry.get('lighting_power', 0)
        temperature = telemetry.get('temperature', 20)
        
        # Use flexibility estimator
        budgets = self.flexibility_estimator.estimate(
            display_freezer_power=telemetry.get('display_freezer_power', 0),
            display_refrigerator_power=telemetry.get('display_refrigerator_power', 0),
            cold_room_power=telemetry.get('cold_room_power', 0),
            freezer_room_power=telemetry.get('freezer_room_power', 0),
            hvac_power=hvac,
            lighting_power=lighting,
            checkout_power=telemetry.get('checkout_power', 0),
            it_power=telemetry.get('it_power', 0),
            other_appliance_power=telemetry.get('other_appliance_power', 0),
            temperature=temperature,
        )
        
        # Extract budgets from list by group name
        budgets_dict = {b.group: b for b in budgets}
        
        return {
            'hvac_soft_shed_kw': budgets_dict.get('hvac', type('obj', (), {'max_reduction_kw': 0})).max_reduction_kw,
            'lighting_shed_kw': budgets_dict.get('lighting', type('obj', (), {'max_reduction_kw': 0})).max_reduction_kw,
            'checkout_shed_kw': budgets_dict.get('checkout', type('obj', (), {'max_reduction_kw': 0})).max_reduction_kw,
            'other_shed_kw': budgets_dict.get('other_appliance', type('obj', (), {'max_reduction_kw': 0})).max_reduction_kw,
        }


def main():
    """Main entry point for forecasting service."""
    import os
    
    logger.info("=" * 60)
    logger.info("🚀 Starting Forecasting Microservice")
    logger.info("=" * 60)
    
    # Configuration
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9093')
    training_data = os.getenv('TRAINING_DATA_PATH', 'data/dataset.csv')
    
    logger.info(f"Kafka brokers: {bootstrap_servers}")
    logger.info(f"Training data: {training_data}")
    
    # Create and start service
    try:
        service = ForecastingService(
            bootstrap_servers=bootstrap_servers,
            training_data_path=training_data if Path(training_data).exists() else None
        )
        
        # Graceful shutdown on SIGTERM/SIGINT
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down gracefully...")
            service.shutdown()
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Start processing loop
        logger.info("Starting message processing loop...")
        logger.info("Subscribed to: telemetry.raw")
        logger.info("Publishing to: forecasting.predictions")
        logger.info("")
        
        service.run()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
