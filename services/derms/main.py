#!/usr/bin/env python3
"""
DERMS (Distributed Energy Resource Management System) Microservice
===================================================================
Consumes MPC decisions from Kafka, translates them into physical equipment
dispatch commands using the DERMSDispatcher, and publishes dispatch commands
back to Kafka.

Architecture:
    Kafka (mpc.decisions) → DERMS Service → Kafka (derms.dispatch)

The service is stateless - each message is processed independently using
the DERMSDispatcher from src.derms.dispatch.
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
from src.derms.dispatch import DERMSDispatcher
from src.mpc.coordinator import MPCAction

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DERMSService(MessageProcessor):
    """
    DERMS microservice that processes MPC decision events.
    
    For each MPC decision event:
    1. Reconstruct MPCAction object from JSON fields
    2. Translate into physical dispatch commands using DERMSDispatcher
    3. Convert DispatchResult into equipment control commands
    4. Publish commands to Kafka for execution
    """
    
    def __init__(
        self,
        bootstrap_servers: str | None = None
    ):
        """
        Initialize DERMS service with dispatcher.
        
        Parameters
        ----------
        bootstrap_servers : str, optional
            Kafka broker addresses
        """
        super().__init__(
            input_topics=['mpc.decisions'],
            output_topic='derms.dispatch',
            group_id='derms-service',
            bootstrap_servers=bootstrap_servers
        )
        
        # Initialize DERMS dispatcher with default battery limits
        self.dispatcher = DERMSDispatcher(
            max_charge_kw=50.0,
            max_discharge_kw=50.0,
            soc_min=10.0,
            soc_max=95.0
        )
        
        logger.info("DERMS service initialized successfully")
    
    def process_message(self, message: Any) -> dict | None:
        """
        Process an MPC decision event and generate equipment dispatch commands.
        
        Parameters
        ----------
        message : kafka.consumer.fetched.ConsumerRecord
            Kafka message containing MPC decision data
        
        Returns
        -------
        dict
            Dispatch event to publish to derms.dispatch topic containing
            equipment commands with setpoints and durations
        """
        decision = message.value
        timestamp = decision.get('timestamp')
        
        logger.debug(f"Processing MPC decision for {timestamp}")
        
        try:
            # Reconstruct MPCAction object from JSON fields
            action = MPCAction(
                peak_shave=decision.get('peak_shave', False),
                peak_shave_kw=decision.get('peak_shave_kw', 0.0),
                load_shift_hvac=decision.get('load_shift_hvac', False),
                hvac_shed_kw=decision.get('hvac_shed_kw', 0.0),
                valley_fill=decision.get('valley_fill', False),
                valley_fill_kw=decision.get('valley_fill_kw', 0.0),
                hard_shed_tiers=decision.get('hard_shed_tiers', []),
                hard_shed_kw=decision.get('hard_shed_kw', 0.0),
                active_action_names=decision.get('active_action_names', [])
            )
            
            # TODO: Phase 4 state service integration — These hardcoded defaults should
            # come from a state service that maintains real-time telemetry. The DERMS
            # service should consume both mpc.decisions and telemetry.state topics and
            # join them by timestamp to get accurate current state values. Current approach
            # produces valid but potentially suboptimal dispatch commands.
            battery_soc = 50.0  # 50% state of charge
            battery_capacity = 200.0  # 200 kWh capacity
            pv_power = 0.0  # no PV generation
            total_consumption = 100.0  # typical supermarket load
            current_grid_power = 0.0  # baseline grid import
            current_p2p = 0.0  # no P2P trading
            
            # Call dispatcher to compute physically feasible dispatch
            dispatch_result = self.dispatcher.dispatch(
                action=action,
                total_consumption=total_consumption,
                pv_power=pv_power,
                battery_soc=battery_soc,
                battery_capacity=battery_capacity,
                current_grid_power=current_grid_power,
                current_p2p=current_p2p
            )
            
            # Convert DispatchResult into equipment control commands
            commands = []
            
            # Battery command
            if dispatch_result.battery_power != 0.0:
                battery_cmd = {
                    'equipment_id': 'battery_001',
                    'command_type': 'charge' if dispatch_result.battery_power < 0 else 'discharge',
                    'setpoint_kw': abs(dispatch_result.battery_power),
                    'duration_min': 15
                }
                commands.append(battery_cmd)
            
            # Grid command
            if dispatch_result.grid_power != 0.0:
                grid_cmd = {
                    'equipment_id': 'grid_connection',
                    'command_type': 'import' if dispatch_result.grid_power > 0 else 'export',
                    'setpoint_kw': abs(dispatch_result.grid_power),
                    'duration_min': 15
                }
                commands.append(grid_cmd)
            
            # HVAC shed command
            if action.hvac_shed_kw > 0:
                hvac_cmd = {
                    'equipment_id': 'hvac_main',
                    'command_type': 'reduce_power',
                    'setpoint_kw': action.hvac_shed_kw,
                    'duration_min': 15
                }
                commands.append(hvac_cmd)
            
            # Lighting shed command (hard shedding)
            if action.hard_shed_kw > 0:
                lighting_cmd = {
                    'equipment_id': 'lighting_zone_1',
                    'command_type': 'dim',
                    'setpoint_percent': 70,
                    'duration_min': 15
                }
                commands.append(lighting_cmd)
            
            # Build output message
            dispatch = {
                'timestamp': timestamp,
                'commands': commands,
                'total_commands': len(commands),
                'battery_power': dispatch_result.battery_power,
                'grid_power': dispatch_result.grid_power,
                'p2p_energy': dispatch_result.p2p_energy,
                'shed_kw': dispatch_result.shed_kw,
                'battery_soc_after': dispatch_result.battery_soc_after,
                'service': 'derms',
            }
            
            logger.debug(f"DERMS dispatch for {timestamp}: {len(commands)} commands, "
                        f"battery={dispatch_result.battery_power:.1f} kW, "
                        f"grid={dispatch_result.grid_power:.1f} kW")
            
            return dispatch
        
        except Exception as e:
            logger.error(f"Error processing message for {timestamp}: {e}", exc_info=True)
            return None


def main():
    """Main entry point for DERMS service."""
    logger.info("=" * 60)
    logger.info("🚀 Starting DERMS Microservice")
    logger.info("=" * 60)
    
    # Configuration
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9093')
    
    logger.info(f"Kafka brokers: {bootstrap_servers}")
    
    # Create and start service
    try:
        service = DERMSService(
            bootstrap_servers=bootstrap_servers
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
        logger.info("Subscribed to: mpc.decisions")
        logger.info("Publishing to: derms.dispatch")
        logger.info("")
        
        service.run()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
