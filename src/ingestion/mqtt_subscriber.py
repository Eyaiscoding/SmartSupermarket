"""
MQTT Subscriber (Dual-Mode Ingestion)
======================================
Subscribes to the ``supermarket/telemetry`` MQTT topic and buffers
incoming rows for the pipeline to consume.  This is the "live/demo"
ingestion mode.  The existing CSV mode remains the default for tests.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from typing import Optional

import pandas as pd

from src.config import settings

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # type: ignore[assignment]


class MQTTSubscriber:
    """Subscribes to MQTT telemetry and buffers rows in a thread-safe deque."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        topic: str | None = None,
        max_buffer: int = 1000,
    ) -> None:
        if mqtt is None:
            raise ImportError("paho-mqtt is required for MQTT ingestion mode")

        self.host = host or settings.MQTT_BROKER_HOST
        self.port = port or settings.MQTT_BROKER_PORT
        self.topic = topic or settings.MQTT_TOPIC
        self.buffer: deque[dict] = deque(maxlen=max_buffer)
        self._client: Optional[mqtt.Client] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            self.buffer.append(payload)
        except Exception as exc:
            logger.warning("Bad MQTT message: %s", exc)

    def start(self) -> None:
        """Connect to the broker and start receiving in background."""
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.MQTT_CLIENT_ID,
        )
        self._client.on_message = self._on_message
        self._client.connect(self.host, self.port, keepalive=60)
        self._client.subscribe(self.topic, qos=1)
        self._client.loop_start()
        self._running = True
        logger.info("MQTT subscriber started on %s:%s topic=%s",
                     self.host, self.port, self.topic)

    def stop(self) -> None:
        """Disconnect and stop the background loop."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        self._running = False
        logger.info("MQTT subscriber stopped.")

    def drain(self) -> list[dict]:
        """Return and clear all buffered messages."""
        items = list(self.buffer)
        self.buffer.clear()
        return items

    def drain_as_dataframe(self) -> pd.DataFrame:
        """Drain buffer and return as a DataFrame matching the dataset schema."""
        items = self.drain()
        if not items:
            return pd.DataFrame()
        df = pd.DataFrame(items)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def buffer_size(self) -> int:
        return len(self.buffer)
