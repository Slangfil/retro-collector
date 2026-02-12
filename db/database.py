import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Item, ItemImage, Platform, PriceRecord

DB_PATH = Path(__file__).parent.parent / "collection.db"

DEFAULT_PLATFORMS = [
    "NES", "SNES", "N64", "GameCube", "Wii",
    "Game Boy", "Game Boy Color", "Game Boy Advance", "DS", "3DS",
    "Mega Drive", "Master System", "Saturn", "Dreamcast", "Game Gear",
    "PlayStation", "PS2", "PS3", "PSP", "PS Vita",
    "Xbox", "Xbox 360",
    "Neo Geo", "PC Engine", "Atari 2600", "Atari 7800",
    "Amiga", "C64",
]


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('game', 'console')),
            platform TEXT NOT NULL,
            condition TEXT,
            notes TEXT,
            for_sale INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS item_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            image_path TEXT NOT NULL,
            is_primary INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS price_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            source TEXT NOT NULL,
            avg_price REAL,
            highest_price REAL,
            lowest_price REAL,
            currency TEXT DEFAULT 'SEK',
            num_results INTEGER,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS platforms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
    """)
    # Seed default platforms
    for name in DEFAULT_PLATFORMS:
        conn.execute(
            "INSERT OR IGNORE INTO platforms (name) VALUES (?)", (name,)
        )
    conn.commit()


# --- Item CRUD ---

def _row_to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        platform=row["platform"],
        condition=row["condition"],
        notes=row["notes"],
        for_sale=bool(row["for_sale"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def add_item(conn: sqlite3.Connection, item: Item) -> int:
    cur = conn.execute(
        """INSERT INTO items (name, type, platform, condition, notes, for_sale)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (item.name, item.type, item.platform, item.condition,
         item.notes, int(item.for_sale)),
    )
    conn.commit()
    return cur.lastrowid


def update_item(conn: sqlite3.Connection, item: Item) -> None:
    conn.execute(
        """UPDATE items SET name=?, type=?, platform=?, condition=?, notes=?,
           for_sale=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (item.name, item.type, item.platform, item.condition,
         item.notes, int(item.for_sale), item.id),
    )
    conn.commit()


def delete_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()


def get_item(conn: sqlite3.Connection, item_id: int) -> Optional[Item]:
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def get_all_items(conn: sqlite3.Connection) -> list[Item]:
    rows = conn.execute(
        "SELECT * FROM items ORDER BY name"
    ).fetchall()
    return [_row_to_item(r) for r in rows]


def toggle_for_sale(conn: sqlite3.Connection, item_id: int) -> bool:
    conn.execute(
        "UPDATE items SET for_sale = 1 - for_sale, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (item_id,),
    )
    conn.commit()
    row = conn.execute("SELECT for_sale FROM items WHERE id=?", (item_id,)).fetchone()
    return bool(row["for_sale"]) if row else False


# --- Image CRUD ---

def add_image(conn: sqlite3.Connection, image: ItemImage) -> int:
    cur = conn.execute(
        """INSERT INTO item_images (item_id, image_path, is_primary, sort_order)
           VALUES (?, ?, ?, ?)""",
        (image.item_id, image.image_path, int(image.is_primary), image.sort_order),
    )
    conn.commit()
    return cur.lastrowid


def get_images_for_item(conn: sqlite3.Connection, item_id: int) -> list[ItemImage]:
    rows = conn.execute(
        "SELECT * FROM item_images WHERE item_id=? ORDER BY sort_order, id",
        (item_id,),
    ).fetchall()
    return [
        ItemImage(
            id=r["id"], item_id=r["item_id"], image_path=r["image_path"],
            is_primary=bool(r["is_primary"]), sort_order=r["sort_order"],
        )
        for r in rows
    ]


def get_primary_image(conn: sqlite3.Connection, item_id: int) -> Optional[ItemImage]:
    row = conn.execute(
        "SELECT * FROM item_images WHERE item_id=? AND is_primary=1 LIMIT 1",
        (item_id,),
    ).fetchone()
    if row:
        return ItemImage(
            id=row["id"], item_id=row["item_id"], image_path=row["image_path"],
            is_primary=True, sort_order=row["sort_order"],
        )
    # Fallback: return first image
    row = conn.execute(
        "SELECT * FROM item_images WHERE item_id=? ORDER BY sort_order LIMIT 1",
        (item_id,),
    ).fetchone()
    if row:
        return ItemImage(
            id=row["id"], item_id=row["item_id"], image_path=row["image_path"],
            is_primary=bool(row["is_primary"]), sort_order=row["sort_order"],
        )
    return None


def set_primary_image(conn: sqlite3.Connection, item_id: int, image_id: int) -> None:
    conn.execute(
        "UPDATE item_images SET is_primary=0 WHERE item_id=?", (item_id,)
    )
    conn.execute(
        "UPDATE item_images SET is_primary=1 WHERE id=? AND item_id=?",
        (image_id, item_id),
    )
    conn.commit()


def delete_image(conn: sqlite3.Connection, image_id: int) -> None:
    conn.execute("DELETE FROM item_images WHERE id=?", (image_id,))
    conn.commit()


def update_image_order(conn: sqlite3.Connection, image_id: int, sort_order: int) -> None:
    conn.execute(
        "UPDATE item_images SET sort_order=? WHERE id=?", (sort_order, image_id)
    )
    conn.commit()


# --- Price records ---

def add_price_record(conn: sqlite3.Connection, record: PriceRecord) -> int:
    cur = conn.execute(
        """INSERT INTO price_records
           (item_id, source, avg_price, highest_price, lowest_price, currency, num_results)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (record.item_id, record.source, record.avg_price, record.highest_price,
         record.lowest_price, record.currency, record.num_results),
    )
    conn.commit()
    return cur.lastrowid


def get_latest_price(conn: sqlite3.Connection, item_id: int) -> Optional[PriceRecord]:
    row = conn.execute(
        "SELECT * FROM price_records WHERE item_id=? ORDER BY fetched_at DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    if not row:
        return None
    return PriceRecord(
        id=row["id"], item_id=row["item_id"], source=row["source"],
        avg_price=row["avg_price"], highest_price=row["highest_price"],
        lowest_price=row["lowest_price"], currency=row["currency"],
        num_results=row["num_results"], fetched_at=row["fetched_at"],
    )


def get_price_history(conn: sqlite3.Connection, item_id: int) -> list[PriceRecord]:
    rows = conn.execute(
        "SELECT * FROM price_records WHERE item_id=? ORDER BY fetched_at DESC",
        (item_id,),
    ).fetchall()
    return [
        PriceRecord(
            id=r["id"], item_id=r["item_id"], source=r["source"],
            avg_price=r["avg_price"], highest_price=r["highest_price"],
            lowest_price=r["lowest_price"], currency=r["currency"],
            num_results=r["num_results"], fetched_at=r["fetched_at"],
        )
        for r in rows
    ]


def get_tradera_calls_today(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM price_records
           WHERE source='tradera' AND date(fetched_at) = date('now')"""
    ).fetchone()
    return row["cnt"] if row else 0


# --- Platforms ---

def get_all_platforms(conn: sqlite3.Connection) -> list[Platform]:
    rows = conn.execute("SELECT * FROM platforms ORDER BY name").fetchall()
    return [Platform(id=r["id"], name=r["name"]) for r in rows]


def add_platform(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute("INSERT OR IGNORE INTO platforms (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def delete_platform(conn: sqlite3.Connection, platform_id: int) -> None:
    conn.execute("DELETE FROM platforms WHERE id=?", (platform_id,))
    conn.commit()
