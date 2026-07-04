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
        if item.type == "console":
            # "PlayStation 5 konsol" instead of "PlayStation 5 PlayStation 5"
            return f"{item.name} konsol"
        parts = [item.name, item.platform]
        return " ".join(p for p in parts if p)

    def lookup_price(self, item: Item, use_tradera: bool = True) -> Optional[PriceRecord]:
        """Look up price for an item (network only, no DB writes).

        Uses the Claude valuation agent. Falls back to Tradera/eBay if Claude fails.
        Returns a PriceRecord (without id/fetched_at) or None.
        Caller is responsible for saving.
        """
        if not item.name.strip():
            return None

        # Claude primary
        try:
            from services.claude_price_agent import lookup_prices
            result = lookup_prices(item.name, item.platform)
            if any(result.get(k) is not None for k in ("low", "median", "high")):
                return PriceRecord(
                    item_id=item.id,
                    source="claude",
                    avg_price=result["median"],
                    highest_price=result["high"],
                    lowest_price=result["low"],
                    currency=result.get("currency", "SEK"),
                    num_results=0,
                    notes=result.get("explanation", ""),
                )
        except Exception as e:
            log.warning(f"Claude price lookup failed for '{item.name}': {e}")

        # Fallback: Tradera
        query = self._build_query(item)
        if use_tradera and self.tradera_available:
            try:
                result = self._tradera.search_completed_items(query)
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
            except Exception as e:
                log.warning(f"Tradera lookup failed for '{query}': {e}")

        # Fallback: eBay
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
