import sqlite3
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QSplitter, QStatusBar, QToolBar, QVBoxLayout, QWidget, QCheckBox,
)

from db.database import (
    delete_item, get_all_platforms, get_images_for_item, get_item,
    get_primary_image, toggle_for_sale,
)
from db.models import Item
from gui.collection_view import CollectionTableView
from gui.export_dialog import ExportDialog
from gui.import_dialog import ImportDialog
from gui.item_dialog import ItemDialog
from gui.price_panel import PricePanel
from services.price_service import PriceService

IMAGES_DIR = Path(__file__).parent.parent / "images"


class PriceLookupWorker(QThread):
    """Runs price lookup network I/O off the main thread.

    Does NOT touch the database — the main thread saves the result.
    """
    finished = Signal(object)  # PriceRecord or None
    error = Signal(str)

    def __init__(self, price_service: PriceService, item: Item,
                 use_tradera: bool = True):
        super().__init__()
        self.price_service = price_service
        self.item = item
        self.use_tradera = use_tradera

    def run(self):
        try:
            result = self.price_service.lookup_price(
                self.item, use_tradera=self.use_tradera,
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self.price_service = PriceService(conn)
        self._workers: list[PriceLookupWorker] = []

        self.setWindowTitle("Retro Collector")
        self.setMinimumSize(1000, 600)
        self.resize(1200, 700)

        self._build_ui()
        self._update_status_bar()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Toolbar
        toolbar_layout = QHBoxLayout()

        self.add_btn = QPushButton("+ Add Item")
        self.add_btn.clicked.connect(self._on_add_item)
        toolbar_layout.addWidget(self.add_btn)

        self.export_btn = QPushButton("Export Selected")
        self.export_btn.clicked.connect(self._on_export)
        toolbar_layout.addWidget(self.export_btn)

        self.refresh_prices_btn = QPushButton("Refresh Prices")
        self.refresh_prices_btn.clicked.connect(self._on_bulk_refresh)
        toolbar_layout.addWidget(self.refresh_prices_btn)

        self.import_btn = QPushButton("Import Photos")
        self.import_btn.clicked.connect(self._on_import_photos)
        toolbar_layout.addWidget(self.import_btn)

        toolbar_layout.addStretch()
        main_layout.addLayout(toolbar_layout)

        # Filters row
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        filter_layout.addWidget(self.search_edit)

        filter_layout.addWidget(QLabel("Platform:"))
        self.platform_filter = QComboBox()
        self._populate_platform_filter()
        self.platform_filter.currentTextChanged.connect(self._on_platform_filter)
        filter_layout.addWidget(self.platform_filter)

        filter_layout.addWidget(QLabel("Type:"))
        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "game", "console"])
        self.type_filter.currentTextChanged.connect(self._on_type_filter)
        filter_layout.addWidget(self.type_filter)

        self.for_sale_check = QCheckBox("For Sale only")
        self.for_sale_check.stateChanged.connect(self._on_for_sale_filter)
        filter_layout.addWidget(self.for_sale_check)

        main_layout.addLayout(filter_layout)

        # Splitter: table | detail panel
        splitter = QSplitter(Qt.Horizontal)

        self.table_view = CollectionTableView(self.conn)
        self.table_view.item_selected.connect(self._on_item_selected)
        self.table_view.item_double_clicked.connect(self._on_edit_item)
        self.table_view.context_menu_requested.connect(self._on_context_menu)
        splitter.addWidget(self.table_view)

        # Detail panel (right side)
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setMinimumWidth(280)
        detail_scroll.setMaximumWidth(400)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)

        self.detail_title = QLabel("Select an item")
        self.detail_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.detail_title.setWordWrap(True)
        detail_layout.addWidget(self.detail_title)

        self.detail_image = QLabel()
        self.detail_image.setFixedHeight(200)
        self.detail_image.setAlignment(Qt.AlignCenter)
        self.detail_image.setStyleSheet(
            "background: #2a2a2a; border: 1px solid #555; border-radius: 4px;"
        )
        detail_layout.addWidget(self.detail_image)

        # Info fields
        info_group = QGroupBox("Details")
        info_layout = QVBoxLayout(info_group)
        self.info_platform = QLabel("Platform: -")
        self.info_type = QLabel("Type: -")
        self.info_condition = QLabel("Condition: -")
        self.info_notes = QLabel("Notes: -")
        self.info_notes.setWordWrap(True)
        info_layout.addWidget(self.info_platform)
        info_layout.addWidget(self.info_type)
        info_layout.addWidget(self.info_condition)
        info_layout.addWidget(self.info_notes)
        detail_layout.addWidget(info_group)

        # Price panel
        self.price_panel = PricePanel(self.conn)
        self.price_panel.refresh_requested.connect(self._on_refresh_price)
        detail_layout.addWidget(self.price_panel)

        # Action buttons
        action_layout = QHBoxLayout()
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._on_edit_selected)
        action_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete_selected)
        action_layout.addWidget(self.delete_btn)
        detail_layout.addLayout(action_layout)

        self.sale_btn = QPushButton("Toggle For Sale")
        self.sale_btn.setEnabled(False)
        self.sale_btn.clicked.connect(self._on_toggle_sale)
        detail_layout.addWidget(self.sale_btn)

        detail_layout.addStretch()
        detail_scroll.setWidget(detail_widget)
        splitter.addWidget(detail_scroll)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.api_status_label = QLabel()
        self.status_bar.addPermanentWidget(self.api_status_label)

    def _populate_platform_filter(self):
        self.platform_filter.clear()
        self.platform_filter.addItem("All")
        for p in get_all_platforms(self.conn):
            self.platform_filter.addItem(p.name)

    def _update_status_bar(self):
        remaining = self.price_service.tradera_calls_remaining()
        self.api_status_label.setText(f"Tradera API: {remaining}/100 calls remaining today")

    def _on_search_changed(self, text):
        self.table_view.proxy_model.set_search(text)

    def _on_platform_filter(self, text):
        self.table_view.proxy_model.set_platform_filter("" if text == "All" else text)

    def _on_type_filter(self, text):
        self.table_view.proxy_model.set_type_filter("" if text == "All" else text)

    def _on_for_sale_filter(self, state):
        self.table_view.proxy_model.set_for_sale_only(bool(state))

    # --- Item selection ---

    _selected_item: Optional[Item] = None

    def _on_item_selected(self, item: Item):
        self._selected_item = item
        self.edit_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.sale_btn.setEnabled(True)

        self.detail_title.setText(item.name)
        self.info_platform.setText(f"Platform: {item.platform}")
        self.info_type.setText(f"Type: {item.type.capitalize()}")
        self.info_condition.setText(f"Condition: {item.condition or '-'}")
        self.info_notes.setText(f"Notes: {item.notes or '-'}")

        # Load primary image
        img = get_primary_image(self.conn, item.id)
        if img:
            path = IMAGES_DIR / img.image_path
            if path.exists():
                pm = QPixmap(str(path)).scaled(
                    280, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                self.detail_image.setPixmap(pm)
            else:
                self.detail_image.setText("Image not found")
        else:
            self.detail_image.clear()
            self.detail_image.setText("No image")

        self.price_panel.update_for_item(item.id)

    # --- CRUD actions ---

    def _on_add_item(self):
        dlg = ItemDialog(self.conn, parent=self)
        if dlg.exec() == ItemDialog.Accepted and dlg.item:
            self.table_view.refresh()
            self._populate_platform_filter()
            # Auto price lookup for new items
            self._start_price_lookup(dlg.item)

    def _on_import_photos(self):
        dlg = ImportDialog(self.conn, parent=self)
        dlg.items_imported.connect(self._on_import_done)
        dlg.exec()

    def _on_import_done(self):
        self.table_view.refresh()
        self._populate_platform_filter()

    def _on_edit_item(self, item: Item):
        fresh = get_item(self.conn, item.id)
        if not fresh:
            return
        dlg = ItemDialog(self.conn, item=fresh, parent=self)
        if dlg.exec() == ItemDialog.Accepted:
            self.table_view.refresh()
            self._populate_platform_filter()
            if self._selected_item and self._selected_item.id == item.id:
                self._on_item_selected(get_item(self.conn, item.id))

    def _on_edit_selected(self):
        if self._selected_item:
            self._on_edit_item(self._selected_item)

    def _on_delete_selected(self):
        if not self._selected_item:
            return
        reply = QMessageBox.question(
            self, "Delete Item",
            f"Delete '{self._selected_item.name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_item(self.conn, self._selected_item.id)
            self._selected_item = None
            self.table_view.refresh()
            self.edit_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.sale_btn.setEnabled(False)
            self.detail_title.setText("Select an item")
            self.detail_image.clear()
            self.price_panel.clear()

    def _on_toggle_sale(self):
        if self._selected_item:
            new_val = toggle_for_sale(self.conn, self._selected_item.id)
            self._selected_item.for_sale = new_val
            self.table_view.refresh()

    # --- Context menu ---

    def _on_context_menu(self, item: Item, pos):
        menu = QMenu(self)
        edit_action = menu.addAction("Edit")
        delete_action = menu.addAction("Delete")
        menu.addSeparator()
        sale_text = "Unmark For Sale" if item.for_sale else "Mark For Sale"
        sale_action = menu.addAction(sale_text)
        menu.addSeparator()
        price_action = menu.addAction("Lookup Price")

        action = menu.exec(pos)
        if action == edit_action:
            self._on_edit_item(item)
        elif action == delete_action:
            self._selected_item = item
            self._on_delete_selected()
        elif action == sale_action:
            toggle_for_sale(self.conn, item.id)
            self.table_view.refresh()
        elif action == price_action:
            self._start_price_lookup(item)

    # --- Price lookup ---

    def _on_refresh_price(self, item_id: int):
        item = get_item(self.conn, item_id)
        if item:
            self._start_price_lookup(item)

    def _start_price_lookup(self, item: Item):
        self.status_bar.showMessage(f"Looking up price for '{item.name}'...", 0)
        # Check quota on the main thread (DB access) before spawning worker
        use_tradera = (self.price_service.tradera_available
                       and self.price_service.tradera_calls_remaining() > 0)
        worker = PriceLookupWorker(self.price_service, item,
                                   use_tradera=use_tradera)
        worker.finished.connect(lambda result: self._on_price_result(item, result))
        worker.error.connect(lambda err: self._on_price_error(item, err))
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        worker.error.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _on_price_result(self, item: Item, result):
        # Save to DB on the main thread
        if result:
            self.price_service.save_price_record(result)
        self.table_view.refresh()
        self._update_status_bar()
        if result:
            self.status_bar.showMessage(
                f"Price for '{item.name}': {int(result.avg_price)} {result.currency} avg "
                f"({result.num_results} results from {result.source})", 5000,
            )
        else:
            self.status_bar.showMessage(f"No price data found for '{item.name}'", 5000)
        if self._selected_item and self._selected_item.id == item.id:
            self.price_panel.update_for_item(item.id)

    def _on_price_error(self, item: Item, error: str):
        self._update_status_bar()
        self.status_bar.showMessage(f"Price lookup failed for '{item.name}': {error}", 5000)

    def _cleanup_worker(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    # --- Bulk operations ---

    def _on_bulk_refresh(self):
        items = self.table_view.selected_items()
        if not items:
            QMessageBox.information(self, "No Selection", "Select items to refresh prices for.")
            return
        if len(items) > 50:
            remaining = self.price_service.tradera_calls_remaining()
            reply = QMessageBox.warning(
                self, "Large Batch",
                f"You selected {len(items)} items. "
                f"Tradera API has {remaining} calls remaining today.\n\n"
                f"Continue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        for item in items:
            self._start_price_lookup(item)

    def _on_export(self):
        items = self.table_view.selected_items()
        if not items:
            # Fall back to all for-sale items
            from db.database import get_all_items
            all_items = get_all_items(self.conn)
            items = [i for i in all_items if i.for_sale]
        if not items:
            QMessageBox.information(
                self, "Nothing to Export",
                "Select items or mark items as 'For Sale' first.",
            )
            return
        dlg = ExportDialog(self.conn, items, parent=self)
        dlg.exec()
