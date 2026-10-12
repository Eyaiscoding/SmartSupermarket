"""Feature-gated adapter shared by API and CLI pipeline entrypoints."""

from .config import MarketConfig, enabled
from .loader import NeighborBook, load_neighbors
from .matching import match_neighbors


class NeighborMarket:
    def __init__(self, book: NeighborBook, config: MarketConfig):
        self.book = book
        self.config = config

    @classmethod
    def for_run(cls, timestamps):
        if not enabled():
            return None
        return cls(
            load_neighbors(expected_timestamps=timestamps), MarketConfig.from_env()
        )

    def settle(self, timestamp, grid_power: float, buy_price: float) -> dict:
        neighbors = self.book.at(timestamp)
        result = match_neighbors(grid_power, buy_price, neighbors, self.config).to_dict()
        result["neighbors"] = [{"id": n.building_id, "type": n.building_type,
            "distance_km": n.distance_km, "production_type": n.production_type,
            "offer_kw": n.energy_offer_kw,
            "deficit_kw": max(n.consumption_kw - n.production, 0)} for n in neighbors]
        return result
