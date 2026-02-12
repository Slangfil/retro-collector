import sqlite3
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal,
)
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QHeaderView, QMenu, QTableView

from db.database import (
    delete_item, get_all_items, get_latest_price, get_primary_image, toggle_for_sale,
)
from db.models import Item

IMAGES_DIR = Path(__file__).parent.parent / "images"
COLUMNS = ["", "Name", "Type", "Platform", "Condition", "Avg Price", "For Sale"]
COL_THUMB = 0
COL_NAME = 1
COL_TYPE = 2
COL_PLATFORM = 3
COL_CONDITION = 4
COL_PRICE = 5
COL_FOR_SALE = 6
THUMB_SIZE = 40


class CollectionModel(QAbstractTableModel):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._items: list[Item] = []
        self._prices: dict[int, Optional[float]] = {}
        self._thumbs: dict[int, Optional[QPixmap]] = {}
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self._items = get_all_items(self.conn)
        self._prices.clear()
        self._thumbs.clear()
        for item in self._items:
            price_rec = get_latest_price(self.conn, item.id)
            self._prices[item.id] = price_rec.avg_price if price_rec else None
            img = get_primary_image(self.conn, item.id)
            if img:
                path = IMAGES_DIR / img.image_path
                if path.exists():
                    pm = QPixmap(str(path)).scaled(
                        THUMB_SIZE, THUMB_SIZE, Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    self._thumbs[item.id] = pm
                else:
                    self._thumbs[item.id] = None
            else:
                self._thumbs[item.id] = None
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == COL_NAME:
                return item.name
            if col == COL_TYPE:
                return item.type.capitalize()
            if col == COL_PLATFORM:
                return item.platform
            if col == COL_CONDITION:
                return item.condition or ""
            if col == COL_PRICE:
                p = self._prices.get(item.id)
                return f"{int(p)}" if p else ""
            if col == COL_FOR_SALE:
                return "Yes" if item.for_sale else ""

        if role == Qt.DecorationRole and col == COL_THUMB:
            return self._thumbs.get(item.id)

        if role == Qt.TextAlignmentRole:
            if col == COL_PRICE:
                return Qt.AlignRight | Qt.AlignVCenter
            if col == COL_FOR_SALE:
                return Qt.AlignCenter

        if role == Qt.UserRole:
            return item

        return None

    def get_item(self, row: int) -> Optional[Item]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class CollectionFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""
        self._platform_filter = ""
        self._type_filter = ""
        self._for_sale_only = False

    def set_search(self, text: str):
        self._search_text = text.lower()
        self.invalidateFilter()

    def set_platform_filter(self, platform: str):
        self._platform_filter = platform
        self.invalidateFilter()

    def set_type_filter(self, item_type: str):
        self._type_filter = item_type
        self.invalidateFilter()

    def set_for_sale_only(self, enabled: bool):
        self._for_sale_only = enabled
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        item = model.get_item(source_row)
        if not item:
            return False

        if self._search_text and self._search_text not in item.name.lower():
            return False
        if self._platform_filter and item.platform != self._platform_filter:
            return False
        if self._type_filter and item.type != self._type_filter:
            return False
        if self._for_sale_only and not item.for_sale:
            return False

        return True

    def lessThan(self, left, right):
        col = left.column()
        if col == COL_PRICE:
            lv = left.data(Qt.DisplayRole)
            rv = right.data(Qt.DisplayRole)
            try:
                return float(lv or 0) < float(rv or 0)
            except (ValueError, TypeError):
                return False
        return super().lessThan(left, right)


class CollectionTableView(QTableView):
    item_selected = Signal(object)  # emits Item
    item_double_clicked = Signal(object)  # emits Item
    context_menu_requested = Signal(object, object)  # emits Item, QPoint

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._model = CollectionModel(conn)
        self._proxy = CollectionFilterProxy()
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.setModel(self._proxy)

        self.setSortingEnabled(True)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.verticalHeader().setVisible(False)

        header = self.horizontalHeader()
        header.setSectionResizeMode(COL_THUMB, QHeaderView.Fixed)
        header.resizeSection(COL_THUMB, THUMB_SIZE + 8)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for col in (COL_TYPE, COL_PLATFORM, COL_CONDITION, COL_PRICE, COL_FOR_SALE):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        self.verticalHeader().setDefaultSectionSize(THUMB_SIZE + 4)

        self.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self.doubleClicked.connect(self._on_double_click)
        self.customContextMenuRequested.connect(self._on_context_menu)

    @property
    def source_model(self) -> CollectionModel:
        return self._model

    @property
    def proxy_model(self) -> CollectionFilterProxy:
        return self._proxy

    def refresh(self):
        self._model.refresh()

    def selected_items(self) -> list[Item]:
        items = []
        for index in self.selectionModel().selectedRows():
            source_index = self._proxy.mapToSource(index)
            item = self._model.get_item(source_index.row())
            if item:
                items.append(item)
        return items

    def _on_row_changed(self, current, previous):
        if not current.isValid():
            return
        source_index = self._proxy.mapToSource(current)
        item = self._model.get_item(source_index.row())
        if item:
            self.item_selected.emit(item)

    def _on_double_click(self, index):
        source_index = self._proxy.mapToSource(index)
        item = self._model.get_item(source_index.row())
        if item:
            self.item_double_clicked.emit(item)

    def _on_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
        source_index = self._proxy.mapToSource(index)
        item = self._model.get_item(source_index.row())
        if item:
            self.context_menu_requested.emit(item, self.viewport().mapToGlobal(pos))
