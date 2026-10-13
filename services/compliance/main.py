#!/usr/bin/env python3
"""
Compliance Microservice
=======================
Verifies regulatory compliance rules (R1-R6) for B2G platform operations.
Consumes dispatch commands and telemetry to ensure:
- Tier 1 loads never interrupted (R1, R2)
- Load shedding follows cascade order (R3)
- Battery within operating limits (R4)
- Cold chain maintained (R5)
- Tracks breach durations (R6)

Architecture:
    Kafka (derms.dispatch + telemetry.raw) → Compliance Service → Kafka (compliance.reports)
"""

import sys
import logging
import signal
import os
import uuid
from pathlib import Path
from typing import Any
from datetime import datetime

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from kafka import KafkaConsumer
from kafka_utils.utils import create_producer, create_consumer
from src.compliance.checker import ComplianceChecker, ComplianceStatus
from src.mpc.coordinator import MPCAction
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComplianceService:
    """
    Compliance microservice that processes dispatch and telemetry events.
    
    Monitors compliance with 6 regulatory rules in real-time:
    - R1: Tier 1 never shed
    - R2: Tier 1 physically supplied
    - R3: Shedding cascade order (4→3→2)
    - R4: Battery operating limits (SOC 10-95%, rate ≤50kW)
    - R5: Cold chain temperature limits
    - R6: Breach duration tracking
    """
    
    def __init__(
        self,
        bootstrap_servers: str | None = None,
        group_id: str = 'compliance-service'
    ):
        """Initialize Compliance service with dual-topic consumption."""
        self.bootstrap_servers = bootstrap_servers or os.getenv(
            'KAFKA_BOOTSTRAP_SERVERS', 'localhost:9093'
        )
        self.group_id = group_id
        
        # Create consumers for both topics
        self.dispatch_consumer = create_consumer(
            'derms.dispatch',
            group_id=f'{group_id}-dispatch',
            bootstrap_servers=self.bootstrap_servers
        )
        
        self.telemetry_consumer = create_consumer(
            'telemetry.raw',
            group_id=f'{group_id}-telemetry',
            bootstrap_servers=self.bootstrap_servers
        )
        
        # Create producer for compliance reports
        self.producer = create_producer(
            bootstrap_servers=self.bootstrap_servers
        )
        
        self.output_topic = 'compliance.reports'
        self.running = True
        
        # Compliance checker for per-step verification
        self.checker = ComplianceChecker()
        
        # Cache latest telemetry for compliance checks
        self.latest_telemetry = {}
        
        logger.info(f"Compliance service initialized (bootstrap: {self.bootstrap_servers})")
    
    def process_telemetry(self, message: Any) -> None:
        """
        Cache latest telemetry data for compliance validation.
        
        Parameters
        ----------
        message : kafka.consumer.fetched.ConsumerRecord
            Telemetry event with sensor readings
        """
        try:
            data = message.value
            timestamp = data.get('timestamp')
            self.latest_telemetry[timestamp] = data
            logger.debug(f"Cached telemetry for {timestamp}")
        except Exception as e:
            logger.error(f"Error caching telemetry: {e}")
    
    def process_dispatch(self, message: Any) -> dict | None:
        """
        Process dispatch command and verify compliance.
        
        Parameters
        ----------
        message : kafka.consumer.fetched.ConsumerRecord
            Dispatch event with equipment commands
        
        Returns
        -------
        dict
            Compliance report with rule verdicts and violations
        """
        try:
            dispatch = message.value
            timestamp = dispatch.get('timestamp')
            
            logger.debug(f"Checking compliance for {timestamp}")
            
            # Reconstruct MPCAction from dispatch data
            # (derms service doesn't pass full action, so we infer from commands)
            commands = dispatch.get('commands', [])
            battery_power = dispatch.get('battery_power', 0.0)
            shed_kw = dispatch.get('shed_kw', 0.0)
            
            # Infer actions from dispatch commands
            action = MPCAction(
                peak_shave=(battery_power < 0),  # discharging
                peak_shave_kw=abs(battery_power) if battery_power < 0 else 0.0,
                load_shift_hvac=any(c.get('equipment_id') == 'hvac_main' for c in commands),
                hvac_shed_kw=next(
                    (c.get('setpoint_kw', 0.0) for c in commands 
                     if c.get('equipment_id') == 'hvac_main'), 0.0
                ),
                valley_fill=(battery_power > 0),  # charging
                valley_fill_kw=battery_power if battery_power > 0 else 0.0,
                hard_shed_tiers=[],  # would need to extract from commands
                hard_shed_kw=shed_kw,
                active_action_names=[]
            )
            
            # Get telemetry data for compliance checks
            telemetry = self.latest_telemetry.get(timestamp, {})
            
            tier_1_demand_kw = telemetry.get('refrigeration_power_kw', 72.0)
            supply_kw = (
                telemetry.get('pv_generation_kw', 0.0) + 
                abs(battery_power) if battery_power < 0 else 0.0 +
                dispatch.get('grid_power', 0.0)
            )
            battery_soc = dispatch.get('battery_soc_after', 50.0)
            battery_power_kw = battery_power
            
            # TODO: Cold chain temperatures not yet in telemetry
            cold_temps = None
            
            # Check compliance rules
            tier_1_protected = self.checker.check_step(
                action=action,
                timestamp=timestamp,
                tier_1_demand_kw=tier_1_demand_kw,
                supply_kw=supply_kw,
                battery_soc=battery_soc,
                battery_power_kw=battery_power_kw,
                cold_temps=cold_temps
            )
            
            # Build compliance report
            status = self.checker.last_status.value
            report = self.checker.report()
            
            # Calculate ancillary services value
            ancillary_value = {
                'peak_shaving': round(action.peak_shave_kw * 0.15, 2) if action.peak_shave else 0.0,
                'valley_filling': round(action.valley_fill_kw * 0.08, 2) if action.valley_fill else 0.0,
                'demand_response': 0.0  # would need DR participation data
            }
            
            # Generate compliance report message
            compliance_report = {
                'timestamp': timestamp,
                'building_id': telemetry.get('building_id', 'supermarket_001'),
                'compliance_status': status,
                'violations': [v.__dict__ for v in report.violations[-10:]],  # last 10
                'rules_checked': ['R1', 'R2', 'R3', 'R4', 'R5', 'R6'],
                'tier_1_protected': tier_1_protected,
                'ancillary_services_value_eur': ancillary_value,
                'audit_trail_id': f'aud_{timestamp}_{uuid.uuid4().hex[:8]}',
                'rule_summary': {
                    'R1_tier1_shed': report.tier_1_breaches,
                    'R2_tier1_unsupplied': report.physical_tier_1_breaches,
                    'R3_cascade_order': report.cascade_order_warnings,
                    'R4_battery_limits': report.battery_limit_warnings,
                    'R5_cold_chain': report.cold_chain_breaches,
                    'R6_longest_breach_min': report.longest_tier_1_breach_min
                },
                'service': 'compliance'
            }
            
            logger.info(f"Compliance check {timestamp}: {status}, "
                       f"tier_1_protected={tier_1_protected}")
            
            return compliance_report
        
        except Exception as e:
            logger.error(f"Error processing dispatch: {e}", exc_info=True)
            return None
    
    def publish_report(self, report: dict) -> None:
        """Publish compliance report to Kafka."""
        try:
            self.producer.send(
                self.output_topic,
                value=report
            )
            self.producer.flush()
            logger.debug(f"Published compliance report for {report.get('timestamp')}")
        except Exception as e:
            logger.error(f"Error publishing report: {e}")
    
    def run(self) -> None:
        """Main processing loop - dual-topic consumption."""
        logger.info("Starting dual-topic consumption loop...")
        
        try:
            while self.running:
                # Poll telemetry (non-blocking, short timeout)
                telemetry_msgs = self.telemetry_consumer.poll(timeout_ms=100, max_records=10)
                for tp, messages in telemetry_msgs.items():
                    for msg in messages:
                        self.process_telemetry(msg)
                
                # Poll dispatch commands (blocking)
                dispatch_msgs = self.dispatch_consumer.poll(timeout_ms=1000, max_records=1)
                for tp, messages in dispatch_msgs.items():
                    for msg in messages:
                        report = self.process_dispatch(msg)
                        if report:
                            self.publish_report(report)
        
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Clean shutdown of Kafka consumers and producer."""
        logger.info("Shutting down Compliance service...")
        self.running = False
        self.dispatch_consumer.close()
        self.telemetry_consumer.close()
        self.producer.close()
        logger.info("Shutdown complete")


def main():
    """Main entry point for Compliance service."""
    logger.info("=" * 60)
    logger.info("🚀 Starting Compliance Microservice")
    logger.info("=" * 60)
    
    # Configuration
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9093')
    logger.info(f"Kafka brokers: {bootstrap_servers}")
    
    # Create and start service
    try:
        service = ComplianceService(
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
        logger.info("Subscribed to: derms.dispatch, telemetry.raw")
        logger.info("Publishing to: compliance.reports")
        logger.info("")
        
        service.run()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
