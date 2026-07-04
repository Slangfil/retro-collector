"""Claude-powered secondhand price lookup — uses web search/fetch with your valuation prompt."""

import json
import logging
import re

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a used/physical video game valuation assistant for a Swedish collector. "
    "Unless the user explicitly states otherwise, always assume the PAL/European version "
    "of a game — never default to NTSC/USA. "
    "Search for current second-hand market values. Prioritize Swedish marketplaces "
    "(Tradera, Blocket) and report prices in SEK. Also check PriceCharting PAL pricing "
    "and eBay European sold listings for reference, converting to SEK as needed. "
    "Report a price range (low/typical/high) for the conditions available "
    "(loose, CIB, sealed), noting which condition each price reflects and the source. "
    "If NTSC prices are the only data available, note that clearly and apply a discount "
    "(PAL versions typically trade lower than NTSC). "
    "Always state the date you checked. If data is thin, say so rather than guessing. "
    "Do not speculate on digital prices — physical second-hand copies only.\n\n"
    "After your analysis, always end with a machine-readable summary on its own line:\n"
    'PRICE_SUMMARY: {"low": <lowest_SEK_or_null>, "median": <typical_SEK_or_null>, '
    '"high": <highest_SEK_or_null>, "currency": "SEK"}'
)


def lookup_prices(item_name: str, platform: str) -> dict:
    """Look up secondhand prices via the Claude valuation agent.

    Returns dict with: low, median, high (float or None), currency (str),
    explanation (str — the full markdown analysis).
    """
    import anthropic

    client = anthropic.Anthropic()
    query = f"{item_name} {platform}".strip() if platform else item_name

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        tools=[
            {
                "type": "web_search_20260318",
                "name": "web_search",
                "allowed_callers": ["direct"],
                "max_uses": 3,
            },
        ],
        messages=[{"role": "user", "content": query}],
        timeout=90,
    )

    full_text = "\n".join(
        b.text for b in response.content if b.type == "text"
    ).strip()

    # Extract the PRICE_SUMMARY JSON from the last line
    match = re.search(r"PRICE_SUMMARY:\s*(\{[^\n]+\})", full_text)
    summary: dict = {}
    if match:
        try:
            summary = json.loads(match.group(1))
        except json.JSONDecodeError:
            log.warning("Could not parse PRICE_SUMMARY JSON: %s", match.group(1))

    # Explanation = everything before the PRICE_SUMMARY line
    explanation = full_text[: match.start()].strip() if match else full_text

    return {
        "low": _to_float(summary.get("low")),
        "median": _to_float(summary.get("median")),
        "high": _to_float(summary.get("high")),
        "currency": summary.get("currency", "SEK"),
        "explanation": explanation,
    }


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None
