import logging
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

EBAY_SOLD_URL = "https://www.ebay.com/sch/i.html"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)


def search_sold_items(query: str, max_results: int = 50) -> dict:
    """Scrape eBay sold listings for price data.

    Returns dict with keys: avg_price, highest_price, lowest_price,
    num_results, prices, currency.
    """
    params = {
        "_nkw": query,
        "LH_Sold": "1",
        "LH_Complete": "1",
        "_ipg": str(min(max_results, 60)),
    }

    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(EBAY_SOLD_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"eBay request failed: {e}")
        raise

    soup = BeautifulSoup(resp.text, "html.parser")
    prices = []
    currency = "SEK"

    for card in soup.select("li.s-card"):
        title_el = card.select_one(".s-card__title")
        if title_el and title_el.get_text(strip=True) == "Shop on eBay":
            continue  # skip promo cards

        price_el = card.select_one(".s-card__price")
        if not price_el:
            continue
        price_text = price_el.get_text(strip=True)

        # Detect currency from the text
        if "SEK" in price_text:
            currency = "SEK"
        elif "$" in price_text:
            currency = "USD"
        elif "EUR" in price_text or "\u20ac" in price_text:
            currency = "EUR"
        elif "GBP" in price_text or "\u00a3" in price_text:
            currency = "GBP"

        # Handle price ranges like "100.00 SEK to 200.00 SEK"
        if " to " in price_text:
            parts = price_text.split(" to ")
            for part in parts:
                p = _parse_price(part)
                if p:
                    prices.append(p)
        else:
            p = _parse_price(price_text)
            if p:
                prices.append(p)

        if len(prices) >= max_results:
            break

    if not prices:
        return {
            "avg_price": None, "highest_price": None,
            "lowest_price": None, "num_results": 0,
            "prices": [], "currency": currency,
        }

    return {
        "avg_price": round(sum(prices) / len(prices), 2),
        "highest_price": max(prices),
        "lowest_price": min(prices),
        "num_results": len(prices),
        "prices": prices,
        "currency": currency,
    }


def _parse_price(text: str) -> Optional[float]:
    """Extract numeric price from text like '$12.34' or '1,234.56 SEK'."""
    # Remove currency symbols/words but keep digits, dots, commas
    cleaned = re.sub(r"[^\d.,]", "", text)
    # Handle European-style "1.234,56" vs US-style "1,234.56"
    if "," in cleaned and "." in cleaned:
        if cleaned.rindex(",") > cleaned.rindex("."):
            # European: 1.234,56
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # US: 1,234.56
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Could be "1,234" (thousands) or "12,34" (decimal)
        # If exactly 2 digits after comma, treat as decimal
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None
