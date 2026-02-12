import sqlite3
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from db.database import get_latest_price
from db.models import Item, PriceRecord


class PricePanel(QWidget):
    refresh_requested = Signal(int)  # item_id

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._current_item_id: Optional[int] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("Price Information")
        glayout = QVBoxLayout(group)

        self.source_label = QLabel("Source: -")
        glayout.addWidget(self.source_label)

        self.avg_label = QLabel("Average: -")
        self.avg_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        glayout.addWidget(self.avg_label)

        self.high_label = QLabel("Highest: -")
        glayout.addWidget(self.high_label)

        self.low_label = QLabel("Lowest: -")
        glayout.addWidget(self.low_label)

        self.results_label = QLabel("Results: -")
        glayout.addWidget(self.results_label)

        self.fetched_label = QLabel("Last checked: -")
        self.fetched_label.setStyleSheet("color: gray;")
        glayout.addWidget(self.fetched_label)

        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Price")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.clicked.connect(self._on_refresh)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        glayout.addLayout(btn_layout)

        layout.addWidget(group)

    def update_for_item(self, item_id: int):
        self._current_item_id = item_id
        self.refresh_btn.setEnabled(True)

        price = get_latest_price(self.conn, item_id)
        if price:
            self._show_price(price)
        else:
            self._show_empty()

    def _show_price(self, price: PriceRecord):
        self.source_label.setText(f"Source: {price.source.capitalize()}")
        if price.avg_price is not None:
            self.avg_label.setText(f"Average: {int(price.avg_price)} {price.currency}")
        else:
            self.avg_label.setText("Average: -")
        if price.highest_price is not None:
            self.high_label.setText(f"Highest: {int(price.highest_price)} {price.currency}")
        else:
            self.high_label.setText("Highest: -")
        if price.lowest_price is not None:
            self.low_label.setText(f"Lowest: {int(price.lowest_price)} {price.currency}")
        else:
            self.low_label.setText("Lowest: -")
        self.results_label.setText(f"Results: {price.num_results}")
        if price.fetched_at:
            self.fetched_label.setText(f"Last checked: {price.fetched_at}")
        else:
            self.fetched_label.setText("Last checked: just now")

    def _show_empty(self):
        self.source_label.setText("Source: -")
        self.avg_label.setText("Average: No price data")
        self.high_label.setText("Highest: -")
        self.low_label.setText("Lowest: -")
        self.results_label.setText("Results: -")
        self.fetched_label.setText("Last checked: -")

    def clear(self):
        self._current_item_id = None
        self.refresh_btn.setEnabled(False)
        self._show_empty()

    def _on_refresh(self):
        if self._current_item_id is not None:
            self.refresh_requested.emit(self._current_item_id)
