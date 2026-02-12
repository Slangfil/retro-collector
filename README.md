# Retro Collector

A desktop app for managing your retro game and console collection, with automatic price lookups from **Tradera** (Swedish auction site) and **eBay**.

Built with Python and PySide6 (Qt). Runs on Linux, macOS, and Windows.

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## What It Does

- **Catalog your collection** — Add games and consoles with platform, condition, notes, and photos
- **Automatic price lookups** — Fetches current market prices from Tradera (via SOAP API) and eBay (via web scraping)
- **Filter and search** — Find items by name, platform, type, or "for sale" status
- **Mark items for sale** — Flag items you want to sell, with suggested prices based on market data
- **Export listings** — Generate sales listing text or CSV, ready to paste into forums or spreadsheets
- **Price history** — Track how prices change over time with stored price records
- **Dark theme** — Catppuccin-inspired dark UI that's easy on the eyes

## Screenshots

*(Add screenshots here by placing images in the repo and linking them)*

## Getting Started

### Prerequisites

You need **Python 3.12 or newer**. Check your version:

```bash
python3 --version
```

### Installation

1. **Clone the repo:**

   ```bash
   git clone https://github.com/Slangfil/retro-collector.git
   cd retro-collector
   ```

2. **Create a virtual environment:**

   ```bash
   python3 -m venv .venv
   ```

3. **Activate it:**

   Linux / macOS:
   ```bash
   source .venv/bin/activate
   ```

   Windows (PowerShell):
   ```powershell
   .venv\Scripts\Activate.ps1
   ```

4. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

   This installs:
   | Package | What it's for |
   |---|---|
   | PySide6 | The GUI framework (Qt for Python) |
   | zeep | SOAP client for the Tradera API |
   | requests | HTTP requests for eBay scraping |
   | beautifulsoup4 | HTML parsing for eBay results |
   | Pillow | Image handling (thumbnails, display) |

### Setting Up Price Lookups

Price lookups are optional — the app works fine without them, you just won't get market prices.

#### Tradera (Swedish auctions)

To get prices from Tradera you need a free API key:

1. Go to [Tradera Developer](https://developer.tradera.com/) and register an application
2. Create a file called `config.json` in the project root:

   ```json
   {
       "tradera": {
           "app_id": 1234,
           "app_key": "your-app-key-here",
           "public_key": "your-public-key-here"
       },
       "currency": "SEK"
   }
   ```

3. Replace the values with your actual keys

> **Note:** The Tradera API has a limit of **100 calls per day** per app. The status bar at the bottom shows how many calls you have left.

#### eBay (international)

eBay lookups work out of the box — no API key needed. The app scrapes eBay's sold listings page to find completed sale prices. If Tradera returns no results for an item, eBay is used as a fallback automatically.

### Running the App

```bash
python main.py
```

The app creates a local SQLite database (`collection.db`) on first run. All your data is stored locally.

## How to Use

### Adding Items

1. Click **"+ Add Item"** in the toolbar
2. Fill in the details:
   - **Name** — The game or console name (e.g. "Super Mario World")
   - **Type** — "game" or "console"
   - **Platform** — Pick from the list or type a custom one (e.g. "SNES", "Mega Drive")
   - **Condition** — Loose, CIB (Complete In Box), Sealed, etc.
   - **Notes** — Any extra info
3. Optionally add photos using the **"Add..."** button in the image section
4. Click **OK** — prices are looked up automatically for new items

### Browsing Your Collection

- The main table shows all items with thumbnails, name, platform, condition, and latest price
- Click any column header to sort
- Use the **search bar** to filter by name
- Use the **Platform** and **Type** dropdowns to narrow results
- Check **"For Sale only"** to see just the items you've flagged for sale
- Click an item to see full details and price info in the right panel
- Double-click to edit

### Price Lookups

- Prices are fetched automatically when you add a new item
- Click **"Refresh Price"** in the detail panel to update a single item
- Select multiple items (Ctrl+click or Shift+click) and click **"Refresh Prices"** for bulk updates
- Right-click any item and choose **"Lookup Price"** from the context menu

The app searches Tradera first, then falls back to eBay if no results are found.

### Exporting for Sale

1. Mark items as "For Sale" using the **"Toggle For Sale"** button or right-click menu
2. Select items and click **"Export Selected"** (or it will auto-select all for-sale items)
3. Choose a format:
   - **Listing Text** — Formatted text with prices, ready for forums or Marketplace
   - **CSV** — For spreadsheets or bulk listing tools
4. Click **"Copy to Clipboard"** and paste wherever you need it

## Supported Platforms

The app comes preloaded with platforms for most retro systems:

NES, SNES, N64, GameCube, Wii, Game Boy, Game Boy Color, Game Boy Advance, DS, 3DS, Mega Drive, Master System, Saturn, Dreamcast, Game Gear, PlayStation, PS2, PS3, PSP, PS Vita, Xbox, Xbox 360, Neo Geo, PC Engine, Atari 2600, Atari 7800, Amiga, C64

You can also type in any custom platform name when adding an item.

## Project Structure

```
retro-collector/
├── main.py                  # Entry point, dark theme, app setup
├── config.json              # Your API keys (not in git!)
├── collection.db            # SQLite database (created on first run)
├── requirements.txt         # Python dependencies
├── images/                  # Stored item photos
├── db/
│   ├── database.py          # All database operations (CRUD)
│   └── models.py            # Data classes: Item, PriceRecord, etc.
├── gui/
│   ├── main_window.py       # Main application window
│   ├── collection_view.py   # Table view with filtering and sorting
│   ├── item_dialog.py       # Add/edit item dialog
│   ├── price_panel.py       # Price display panel
│   └── export_dialog.py     # Export/listing dialog
├── services/
│   ├── price_service.py     # Price lookup orchestrator
│   ├── tradera.py           # Tradera SOAP API client
│   └── ebay.py              # eBay scraper
└── export/
    └── listing_export.py    # Text and CSV formatters
```

## Troubleshooting

**"Tradera API: 0/100 calls remaining"**
The daily limit resets at midnight. You can still get prices from eBay.

**No prices showing up?**
- Check that `config.json` exists and has valid Tradera keys
- Make sure your item name is specific enough (e.g. "Super Metroid" rather than just "Metroid")
- eBay results depend on recent sold listings — obscure items may have none

**App won't start / PySide6 errors on Linux?**
You may need Qt system libraries. On Ubuntu/Debian:
```bash
sudo apt install libxcb-xinerama0 libxcb-cursor0
```

On Arch:
```bash
sudo pacman -S qt6-base
```

**Images not showing?**
Make sure the `images/` folder exists in the project root (it's created automatically on first run).

## Contributing

Pull requests are welcome! If you find a bug or have an idea, open an issue.
