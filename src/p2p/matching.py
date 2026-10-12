"""Deterministic substitution of the DERMS grid residual, without altering supply."""

import math

from .config import MarketConfig
from .models import MarketResult, NeighborStep, Trade
from .pricing import midpoint, wheeling_fee


def match_neighbors(
    grid_power: float,
    buy_price: float,
    neighbors: list[NeighborStep],
    config: MarketConfig | None = None,
) -> MarketResult:
    config = config or MarketConfig()
    if not math.isfinite(grid_power):
        raise ValueError("Grid power must be finite")
    if len({n.building_id for n in neighbors}) != len(neighbors):
        raise ValueError("Duplicate counterparties in one timestep")
    p2p_price = midpoint(buy_price, config)
    buying = grid_power > 0
    remaining = abs(grid_power)
    candidates = []
    for n in neighbors:
        if any(
            not math.isfinite(v) or v < 0
            for v in (n.consumption_kw, n.production, n.energy_offer_kw)
        ):
            raise ValueError("Neighbour quantities must be finite and non-negative")
        fee = wheeling_fee(n.distance_km, config)
        if buying:
            quantity = min(n.energy_offer_kw, max(n.production - n.consumption_kw, 0))
            price = p2p_price * config.production_type_price_factor.get(
                n.production_type, 1.0
            )
            effective = price + fee
            beneficial = effective < buy_price
            order = (effective, -quantity, n.building_id)
        else:
            quantity = max(n.consumption_kw - n.production, 0)
            price = p2p_price
            effective = price - fee
            beneficial = effective > config.sell_price
            order = (-effective, n.distance_km, n.building_id)
        if quantity > 0 and beneficial:
            candidates.append((order, n, quantity, price, fee, effective))
    trades = []
    for _, n, available, price, fee, effective in sorted(
        candidates, key=lambda c: c[0]
    ):
        if remaining <= 0:
            break
        quantity = min(remaining, available)
        kwh = quantity * config.step_hours
        savings = kwh * (
            buy_price - effective if buying else effective - config.sell_price
        )
        trades.append(
            Trade(
                n.building_id,
                n.building_type,
                "buy" if buying else "sell",
                quantity,
                kwh,
                price,
                fee,
                n.distance_km,
                savings,
            )
        )
        remaining = max(remaining - quantity, 0)
    quantity = sum(t.quantity_kw for t in trades)
    p2p_import, p2p_export = (quantity, 0.0) if buying else (0.0, quantity)
    grid_after = remaining if buying else -remaining
    cost = max(grid_after, 0) * config.step_hours * buy_price + sum(
        t.quantity_kwh * (t.price_per_kwh + t.wheeling_fee)
        for t in trades
        if t.direction == "buy"
    )
    revenue = max(-grid_after, 0) * config.step_hours * config.sell_price + sum(
        t.quantity_kwh * (t.price_per_kwh - t.wheeling_fee)
        for t in trades
        if t.direction == "sell"
    )
    return MarketResult(
        grid_after,
        p2p_import - p2p_export,
        p2p_import,
        p2p_export,
        trades,
        sum(t.saving_vs_grid for t in trades),
        cost,
        revenue,
        buy_price,
        config.sell_price,
        p2p_price,
    )


def summarize(records: list[dict]) -> list[dict]:
    totals: dict[str, dict] = {}
    for record in records:
        for trade in record.get("p2p_trades") or []:
            bid = trade["counterparty_id"]
            row = totals.setdefault(
                bid,
                {
                    "counterparty_id": bid,
                    "building_type": trade["building_type"],
                    "bought_kwh": 0.0,
                    "sold_kwh": 0.0,
                    "money_saved": 0.0,
                },
            )
            row["bought_kwh" if trade["direction"] == "buy" else "sold_kwh"] += trade[
                "quantity_kwh"
            ]
            row["money_saved"] += trade["saving_vs_grid"]
    return [totals[key] for key in sorted(totals)]
