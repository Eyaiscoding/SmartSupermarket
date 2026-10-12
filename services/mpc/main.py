#!/usr/bin/env python3
"""
MPC (Model Predictive Control) Microservice
============================================
Consumes forecasting predictions from Kafka, runs the receding-horizon
MPC controller, and publishes action decisions back to Kafka.

Architecture:
    Kafka (forecasting.predictions) → MPC Service → Kafka (mpc.decisions)

The service is stateless - each message is processed independently using
the MPCCoordinator from src.mpc.coordinator.
"""

import sys
import logging
import signal
import os
from pathlib import Path
from typing import Any

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from kafka_utils.utils import MessageProcessor
from src.mpc.coordinator import MPCCoordinator
from src.forecasting.flexibility import FlexBudget

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MPCService(MessageProcessor):
    """
    MPC microservice that processes forecasting prediction events.
    
    For each prediction event:
    1. Extract forecasts (consumption, PV, flexibility budgets)
    2. Run MPC optimization to decide actions (peak shaving, load shifting, etc.)
    3. Publish decisions to Kafka for DERMS to execute
    """
    
    def __init__(
        self,
        bootstrap_servers: str | None = None,
        horizon_hours: int = 24,
        time_step_minutes: int = 15
    ):
        """
        Initialize MPC service with controller.
        
        Parameters
        ----------
        bootstrap_servers : str, optional
            Kafka broker addresses
        horizon_hours : int
            MPC planning horizon in hours
        time_step_minutes : int
            Time discretization step in minutes
        """
        super().__init__(
            input_topics=['forecasting.predictions'],
            output_topic='mpc.decisions',
            group_id='mpc-service',
            bootstrap_servers=bootstrap_servers
        )
        
        # Initialize MPC controller
        self.horizon_steps = (horizon_hours * 60) // time_step_minutes
        logger.info(f"Initializing MPC controller with horizon={self.horizon_steps} steps...")
        self.coordinator = MPCCoordinator(
            horizon=min(self.horizon_steps, 4)  # Cap at 4 steps as per coordinator default
        )
        
        logger.info("MPC service initialized successfully")
    
    def process_message(self, message: Any) -> dict | None:
        """
        Process a forecasting prediction event and generate MPC decision.
        
        Parameters
        ----------
        message : kafka.consumer.fetched.ConsumerRecord
            Kafka message containing forecasting prediction data
        
        Returns
        -------
        dict
            Decision event to publish to mpc.decisions topic
        """
        prediction = message.value
        timestamp = prediction.get('timestamp')
        
        logger.debug(f"Processing prediction for {timestamp}")
        
        try:
            # Extract prediction data
            forecast_consumption = prediction.get('forecast_consumption', 0.0)
            forecast_pv = prediction.get('forecast_pv', 0.0)
            flexibility_budgets = prediction.get('flexibility_budgets', {})
            anomaly_flag = prediction.get('anomaly_flag', False)
            
            # Convert flexibility budgets dict to FlexBudget list
            flex_budgets = self._parse_flexibility_budgets(flexibility_budgets)
            
            # Current state assumptions (in real system, would come from state service)
            # For now, use sensible defaults
            battery_soc = 50.0  # 50% state of charge
            battery_capacity = 200.0  # 200 kWh capacity
            energy_price = 0.20  # €0.20/kWh
            demand_response = 0  # No DR event active
            
            # Build forecast vectors (replicate current forecast for horizon)
            forecast_consumption_vec = [forecast_consumption] * self.coordinator.horizon
            forecast_pv_vec = [forecast_pv] * self.coordinator.horizon
            forecast_prices_vec = [energy_price] * self.coordinator.horizon
            
            # Run MPC optimization
            action = self.coordinator.decide(
                total_consumption=forecast_consumption,
                pv_power=forecast_pv,
                battery_soc=battery_soc,
                battery_capacity=battery_capacity,
                energy_price=energy_price,
                demand_response=demand_response,
                flex_budgets=flex_budgets,
                forecast_consumption=forecast_consumption_vec,
                forecast_pv=forecast_pv_vec,
                forecast_prices=forecast_prices_vec,
            )
            
            # Convert MPCAction to JSON-serializable dict
            decision = {
                'timestamp': timestamp,
                'peak_shave': action.peak_shave,
                'peak_shave_kw': action.peak_shave_kw,
                'load_shift_hvac': action.load_shift_hvac,
                'hvac_shed_kw': action.hvac_shed_kw,
                'valley_fill': action.valley_fill,
                'valley_fill_kw': action.valley_fill_kw,
                'hard_shed_tiers': action.hard_shed_tiers,
                'hard_shed_kw': action.hard_shed_kw,
                'active_action_names': action.active_action_names,
                'total_battery_request_kw': action.total_battery_request_kw,
                'service': 'mpc',
            }
            
            logger.debug(f"MPC decision for {timestamp}: actions={action.active_action_names}, "
                        f"battery={action.total_battery_request_kw:.1f} kW")
            
            return decision
        
        except Exception as e:
            logger.error(f"Error processing message for {timestamp}: {e}", exc_info=True)
            return None
    
    def _parse_flexibility_budgets(self, budgets_dict: dict) -> list[FlexBudget]:
        """
        Convert flexibility budgets dict from forecasting service to FlexBudget list.
        
        Parameters
        ----------
        budgets_dict : dict
            Dictionary with keys like 'hvac_soft_shed_kw', 'lighting_shed_kw', etc.
        
        Returns
        -------
        list[FlexBudget]
            List of FlexBudget objects for MPC coordinator
        """
        flex_budgets = []
        
        # Map budget keys to tier and group name
        budget_mapping = [
            ('hvac_soft_shed_kw', 'hvac', 3, 60.0),  # Tier 3, 60 min duration
            ('lighting_shed_kw', 'lighting', 4, 240.0),  # Tier 4, 240 min duration
            ('checkout_shed_kw', 'checkout', 2, 15.0),  # Tier 2, 15 min duration
            ('other_shed_kw', 'other_appliance', 4, 240.0),  # Tier 4, 240 min duration
        ]
        
        for key, group, tier, duration in budget_mapping:
            shed_capacity = budgets_dict.get(key, 0.0)
            if shed_capacity > 0:
                flex_budgets.append(
                    FlexBudget(
                        group=group,
                        current_power_kw=shed_capacity,  # Approximation: use shed capacity as current power
                        max_reduction_kw=shed_capacity,
                        max_duration_min=duration,
                        tier=tier
                    )
                )
        
        return flex_budgets


def main():
    """Main entry point for MPC service."""
    logger.info("=" * 60)
    logger.info("🚀 Starting MPC Microservice")
    logger.info("=" * 60)
    
    # Configuration
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9093')
    horizon_hours = int(os.getenv('MPC_HORIZON_HOURS', '24'))
    time_step_minutes = int(os.getenv('MPC_TIME_STEP_MINUTES', '15'))
    
    logger.info(f"Kafka brokers: {bootstrap_servers}")
    logger.info(f"MPC horizon: {horizon_hours} hours")
    logger.info(f"Time step: {time_step_minutes} minutes")
    
    # Create and start service
    try:
        service = MPCService(
            bootstrap_servers=bootstrap_servers,
            horizon_hours=horizon_hours,
            time_step_minutes=time_step_minutes
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
        logger.info("Subscribed to: forecasting.predictions")
        logger.info("Publishing to: mpc.decisions")
        logger.info("")
        
        service.run()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
