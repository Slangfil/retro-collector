import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from zeep import Client, xsd
from zeep.helpers import serialize_object

log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.json"

SEARCH_WSDL = "https://api.tradera.com/v3/SearchService.asmx?WSDL"
PUBLIC_WSDL = "https://api.tradera.com/v3/PublicService.asmx?WSDL"


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f).get("tradera", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _remove_outliers(prices: list[float]) -> list[float]:
    """Trim the bottom and top 20% of prices to reduce noise.

    Removes junk listings (accessories, broken items) from the low end
    and bundles from the high end.
    """
    if len(prices) < 5:
        return prices

    sorted_p = sorted(prices)
    trim = max(1, len(sorted_p) // 5)
    return sorted_p[trim:-trim]


class TraderaClient:
    def __init__(self):
        self._config = _load_config()
        self._search_client: Optional[Client] = None
        self._public_client: Optional[Client] = None

    @property
    def app_id(self) -> int:
        return self._config.get("app_id", 0)

    @property
    def app_key(self) -> str:
        return self._config.get("app_key", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_key)

    def _get_search_client(self) -> Client:
        if self._search_client is None:
            self._search_client = Client(SEARCH_WSDL)
        return self._search_client

    def _get_public_client(self) -> Client:
        if self._public_client is None:
            self._public_client = Client(PUBLIC_WSDL)
        return self._public_client

    def _auth_headers(self, client: Client) -> list:
        """Build proper SOAP header elements with correct wrapper names."""
        ns = "http://api.tradera.com"
        auth_type = client.get_type(f"{{{ns}}}AuthenticationHeader")
        conf_type = client.get_type(f"{{{ns}}}ConfigurationHeader")

        auth_header = xsd.Element(
            f"{{{ns}}}AuthenticationHeader", auth_type
        )(AppId=self.app_id, AppKey=self.app_key)
        conf_header = xsd.Element(
            f"{{{ns}}}ConfigurationHeader", conf_type
        )(Sandbox=0, MaxResultAge=0)
        return [auth_header, conf_header]

    def search_completed_items(self, query: str, category_id: int = 0,
                               max_results: int = 50) -> dict:
        """Search for completed/sold items on Tradera using SearchAdvanced.

        Only includes ended auctions that had bids (i.e. actually sold).
        MaxBid on ended items is the final sold price.

        Returns dict with keys: avg_price, highest_price, lowest_price,
        num_results, prices (list of individual prices).
        """
        if not self.is_configured:
            raise ValueError("Tradera API not configured")

        client = self._get_search_client()

        try:
            result = client.service.SearchAdvanced(
                request={
                    "SearchWords": query,
                    "CategoryId": category_id or 0,
                    "ItemStatus": "Ended",
                    "SearchInDescription": False,
                    "OnlyAuctionsWithBuyNow": False,
                    "OnlyItemsWithThumbnail": False,
                    "ItemsPerPage": max_results,
                    "PageNumber": 1,
                    "CountyId": 0,
                },
                _soapheaders=self._auth_headers(client),
            )
        except Exception as e:
            log.error(f"Tradera SearchAdvanced failed: {e}")
            raise

        data = serialize_object(result)
        items = data.get("Items", []) or []
        if not items:
            return {
                "avg_price": None, "highest_price": None,
                "lowest_price": None, "num_results": 0, "prices": [],
            }

        prices = []
        for item in items[:max_results]:
            # Only include items that actually sold (had bids and ended)
            if not item.get("IsEnded"):
                continue
            if not item.get("HasBids"):
                continue

            # MaxBid on an ended auction is the final sold price
            price = item.get("MaxBid") or item.get("BuyItNowPrice")
            if price and price > 0:
                prices.append(float(price))

        prices = _remove_outliers(prices)

        if not prices:
            return {
                "avg_price": None, "highest_price": None,
                "lowest_price": None, "num_results": 0, "prices": [],
            }

        return {
            "avg_price": round(sum(prices) / len(prices), 0),
            "highest_price": max(prices),
            "lowest_price": min(prices),
            "num_results": len(prices),
            "prices": prices,
        }
