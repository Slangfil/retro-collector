import sqlite3
from typing import Optional

from db.database import get_images_for_item, get_latest_price
from db.models import Item, PriceRecord


def format_single_listing(conn: sqlite3.Connection, item: Item,
                          include_images: bool = True) -> str:
    """Format a single item as a sales listing text."""
    lines = []
    lines.append(f"** {item.name} **")
    lines.append(f"Platform: {item.platform}")
    lines.append(f"Type: {item.type.capitalize()}")
    if item.condition:
        lines.append(f"Condition: {item.condition}")

    price = get_latest_price(conn, item.id)
    if price and price.avg_price:
        lines.append(f"Asking price: {int(price.avg_price)} {price.currency}")
        lines.append(f"  (Based on {price.source} avg of {price.num_results} sold items)")

    if item.notes:
        lines.append(f"\n{item.notes}")

    if include_images:
        images = get_images_for_item(conn, item.id)
        if images:
            lines.append("\nImages:")
            for img in images:
                lines.append(f"  - {img.image_path}")

    return "\n".join(lines)


def format_bulk_listing(conn: sqlite3.Connection, items: list[Item],
                        include_images: bool = True) -> str:
    """Format multiple items as a combined sales listing."""
    sections = []
    for item in items:
        sections.append(format_single_listing(conn, item, include_images))

    header = f"=== For Sale: {len(items)} items ===\n"
    return header + "\n\n---\n\n".join(sections)


def format_csv_listing(conn: sqlite3.Connection, items: list[Item]) -> str:
    """Format items as CSV for spreadsheet import."""
    lines = ["Name,Platform,Type,Condition,Avg Price,Currency,Notes"]
    for item in items:
        price = get_latest_price(conn, item.id)
        avg = str(int(price.avg_price)) if price and price.avg_price else ""
        currency = price.currency if price else ""
        notes = item.notes.replace('"', '""') if item.notes else ""
        name = item.name.replace('"', '""')
        lines.append(
            f'"{name}","{item.platform}","{item.type}","{item.condition}",'
            f'{avg},"{currency}","{notes}"'
        )
    return "\n".join(lines)
