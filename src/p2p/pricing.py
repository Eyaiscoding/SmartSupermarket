import math

from .config import MarketConfig


def midpoint(buy_price: float, config: MarketConfig) -> float:
    if not math.isfinite(buy_price):
        raise ValueError("Dataset energy_price must be finite")
    return (buy_price + config.sell_price) / 2


def wheeling_fee(distance_km: float, config: MarketConfig) -> float:
    if not math.isfinite(distance_km) or distance_km < 0:
        raise ValueError("Distance must be finite and non-negative")
    return config.wheeling_base_fee + config.wheeling_per_km * distance_km
