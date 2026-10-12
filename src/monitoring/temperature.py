"""Stateful 15-minute temperature observations; never control refrigeration."""

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

SENSORS = (
    "display_freezer_temp",
    "freezer_room_temp",
    "display_refrigerator_temp",
    "cold_room_temp",
)
TEMPERATURE_OPTIONAL_FIELDS = (
    "temperature_limits",
    "temperatures",
    "temperature_alerts",
    "temperature_status",
)


@dataclass(frozen=True)
class SensorLimits:
    low: float
    high: float
    hard_limit: float

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.low, self.high, self.hard_limit)):
            raise ValueError("Temperature limits must be finite")
        if not self.low < self.high <= self.hard_limit:
            raise ValueError("Temperature limits must satisfy low < high <= hard_limit")


class TemperatureMonitor:
    def __init__(
        self,
        limits: Mapping[str, SensorLimits] | None = None,
        critical_after_steps: int = 2,
    ):
        if isinstance(critical_after_steps, bool) or not isinstance(
            critical_after_steps, int
        ):
            raise TypeError("critical_after_steps must be an integer")
        if critical_after_steps < 1:
            raise ValueError("critical_after_steps must be positive")
        # Simulation placeholders, NOT validated food-safety thresholds. Validate
        # against applicable rules and observed ranges before operational use.
        self.limits = {
            sensor: SensorLimits(-30, -18, -12)
            if "freezer" in sensor
            else SensorLimits(0, 5, 8)
            for sensor in SENSORS
        }
        if limits is not None:
            if set(limits) - set(SENSORS):
                raise ValueError("Unknown temperature sensor")
            self.limits.update(limits)
        self.critical_after_steps = critical_after_steps
        self._excursions: dict[str, tuple[int, str]] = {}
        self._previous: datetime | None = None

    @classmethod
    def from_env(cls):
        defaults = cls()
        limits = {}
        for sensor, band in defaults.limits.items():
            prefix = f"B2G_TEMP_{sensor.removesuffix('_temp').upper()}"
            limits[sensor] = SensorLimits(
                float(os.getenv(f"{prefix}_LOW", str(band.low))),
                float(os.getenv(f"{prefix}_HIGH", str(band.high))),
                float(os.getenv(f"{prefix}_HARD_LIMIT", str(band.hard_limit))),
            )
        return cls(limits, int(os.getenv("B2G_TEMP_CRITICAL_AFTER_STEPS", "2")))

    def observe(self, timestamp: object, readings: Mapping) -> dict:
        instant = datetime.fromisoformat(str(timestamp))
        if instant.tzinfo is not None:
            instant = instant.astimezone(UTC).replace(tzinfo=None)
        if self._previous is not None:
            if instant <= self._previous:
                raise ValueError(
                    "Temperature observations must be strictly chronological"
                )
            if instant - self._previous != timedelta(minutes=15):
                self._excursions.clear()
        self._previous = instant
        temperatures, alerts = {}, []
        for sensor, band in self.limits.items():
            raw = readings.get(sensor)
            try:
                value = float(raw) if raw is not None else float("nan")
            except (TypeError, ValueError):
                value = float("nan")
            if not math.isfinite(value):
                self._excursions.pop(sensor, None)
                continue
            temperatures[sensor] = value
            if band.low <= value <= band.high:
                self._excursions.pop(sensor, None)
                continue
            count, since = self._excursions.get(sensor, (0, instant.isoformat(sep=" ")))
            count += 1
            self._excursions[sensor] = (count, since)
            status = (
                "CRITICAL"
                if value > band.hard_limit or count >= self.critical_after_steps
                else "WARNING"
            )
            alerts.append(
                {
                    "sensor": sensor,
                    "value": value,
                    "status": status,
                    "limit_low": band.low,
                    "limit_high": band.high,
                    "since": since,
                }
            )
        if not temperatures:
            return {}
        overall = (
            "CRITICAL"
            if any(a["status"] == "CRITICAL" for a in alerts)
            else "WARNING"
            if alerts
            else "OK"
        )
        return {
            "temperature_limits": {sensor: {"low": band.low, "high": band.high,
                "hard_limit": band.hard_limit} for sensor, band in self.limits.items()},
            "temperatures": temperatures,
            "temperature_alerts": alerts,
            "temperature_status": overall,
        }
