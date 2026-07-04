from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional



@dataclass
class Item:
    id: Optional[int] = None
    name: str = ""
    type: str = "game"  # 'game' or 'console'
    platform: str = ""
    condition: str = ""
    notes: str = ""
    for_sale: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ItemImage:
    id: Optional[int] = None
    item_id: int = 0
    image_path: str = ""
    is_primary: bool = False
    sort_order: int = 0


@dataclass
class PriceRecord:
    id: Optional[int] = None
    item_id: int = 0
    source: str = ""  # 'tradera', 'ebay', or 'claude'
    avg_price: Optional[float] = None   # median for claude source
    highest_price: Optional[float] = None
    lowest_price: Optional[float] = None
    currency: str = "SEK"
    num_results: int = 0
    fetched_at: Optional[datetime] = None
    notes: str = ""  # full markdown analysis (claude source)


@dataclass
class Platform:
    id: Optional[int] = None
    name: str = ""
