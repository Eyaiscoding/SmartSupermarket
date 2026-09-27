"""
MQTT Telemetry Publisher
=========================
Replays dataset.csv row by row onto an MQTT topic (``supermarket/telemetry``)
at a configurable interval, simulating a live edge sensor feed against a
local Mosquitto broker.

Usage::

    python -m src.ingestion.mqtt_publisher                     # default 0.1s
    python -m src.ingestion.mqtt_publisher --interval 1.0      # 1 row/sec
    python -m src.ingestion.mqtt_publisher --host mosquitto     # Docker name
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt is required. Install with: pip install paho-mqtt")
    sys.exit(1)

# Ensure project root is on path.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion import load_dataset
from src.config import settings


def publish_dataset(
    host: str = "localhost",
    port: int = 1883,
    topic: str = "supermarket/telemetry",
    interval: float = 0.1,
    dataset_path: str | None = None,
) -> None:
    """Replay the dataset one row at a time over MQTT."""

    df = load_dataset(path=dataset_path)
    print(f"Loaded {len(df)} rows, publishing to {topic} at {host}:{port}")
    print(f"Interval: {interval}s per row ({1/interval:.1f} rows/sec)")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="b2g-publisher",
    )
    client.connect(host, port, keepalive=60)
    client.loop_start()

    try:
        for i, row in df.iterrows():
            payload = {
                col: (
                    str(row[col]) if col == "timestamp"
                    else int(row[col]) if col in ("occupancy", "demand_response")
                    else float(row[col])
                )
                for col in df.columns
            }
            client.publish(topic, json.dumps(payload), qos=1)
            if (i + 1) % 500 == 0:
                print(f"  Published {i + 1}/{len(df)} rows")
            time.sleep(interval)

        print(f"Done: {len(df)} rows published.")
    except KeyboardInterrupt:
        print(f"\nStopped at row {i}.")
    finally:
        client.loop_stop()
        client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="MQTT dataset publisher")
    parser.add_argument("--host", default=settings.MQTT_BROKER_HOST)
    parser.add_argument("--port", type=int, default=settings.MQTT_BROKER_PORT)
    parser.add_argument("--topic", default=settings.MQTT_TOPIC)
    parser.add_argument("--interval", type=float, default=0.1,
                        help="Seconds between rows (default: 0.1)")
    parser.add_argument("--dataset", default=None,
                        help="Path to dataset.csv (auto-detected if omitted)")
    args = parser.parse_args()
    publish_dataset(
        host=args.host,
        port=args.port,
        topic=args.topic,
        interval=args.interval,
        dataset_path=args.dataset,
    )


if __name__ == "__main__":
    main()
