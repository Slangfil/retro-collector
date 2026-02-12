import logging
import sqlite3
from typing import Optional

from db.database import add_price_record, get_tradera_calls_today
from db.models import Item, PriceRecord
from services.tradera import TraderaClient
from services import ebay

log = logging.getLogger(__name__)

TRADERA_DAILY_LIMIT = 100


class PriceService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._tradera = TraderaClient()

    @property
    def tradera_available(self) -> bool:
        return self._tradera.is_configured

    def tradera_calls_remaining(self) -> int:
        used = get_tradera_calls_today(self.conn)
        return max(0, TRADERA_DAILY_LIMIT - used)

    def _build_query(self, item: Item) -> str:
        parts = [item.name, item.platform]
        return " ".join(p for p in parts if p)

    def lookup_price(self, item: Item, use_tradera: bool = True) -> Optional[PriceRecord]:
        """Look up price for an item (network only, no DB writes).

        Tries Tradera first, falls back to eBay. Returns a PriceRecord
        (without id/fetched_at) or None. Caller is responsible for saving.
        """
        query = self._build_query(item)
        if not query.strip():
            return None

        # Try Tradera first
        if use_tradera and self.tradera_available:
            try:
                result = self._tradera.search_items(query)
                if result["num_results"] > 0:
                    return PriceRecord(
                        item_id=item.id,
                        source="tradera",
                        avg_price=result["avg_price"],
                        highest_price=result["highest_price"],
                        lowest_price=result["lowest_price"],
                        currency="SEK",
                        num_results=result["num_results"],
                    )
                log.info(f"No Tradera results for '{query}', trying eBay")
            except Exception as e:
                log.warning(f"Tradera lookup failed for '{query}': {e}")

        # Fallback to eBay
        try:
            result = ebay.search_sold_items(query)
            if result["num_results"] > 0:
                return PriceRecord(
                    item_id=item.id,
                    source="ebay",
                    avg_price=result["avg_price"],
                    highest_price=result["highest_price"],
                    lowest_price=result["lowest_price"],
                    currency=result.get("currency", "USD"),
                    num_results=result["num_results"],
                )
        except Exception as e:
            log.warning(f"eBay lookup failed for '{query}': {e}")

        return None

    def save_price_record(self, record: PriceRecord) -> int:
        """Save a price record to DB. Must be called from the main thread."""
        return add_price_record(self.conn, record)
