import sqlite3
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QVBoxLayout, QWidget,
)

from db.database import get_latest_price
from db.models import PriceRecord


class PricePanel(QWidget):
    refresh_requested = Signal(int)  # item_id

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._current_item_id: Optional[int] = None
        self._current_notes: str = ""
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("Price Information")
        glayout = QVBoxLayout(group)

        # Source + date row
        top_row = QHBoxLayout()
        self.source_label = QLabel("Source: -")
        top_row.addWidget(self.source_label)
        top_row.addStretch()
        self.fetched_label = QLabel("")
        self.fetched_label.setStyleSheet("color: gray; font-size: 11px;")
        top_row.addWidget(self.fetched_label)
        glayout.addLayout(top_row)

        # Three-column price display: Low | Median/Avg | High
        price_row = QHBoxLayout()

        self._low_box   = self._make_price_col("Low")
        self._mid_box   = self._make_price_col("Median")
        self._high_box  = self._make_price_col("High")

        price_row.addWidget(self._low_box["widget"])
        price_row.addWidget(self._mid_box["widget"])
        price_row.addWidget(self._high_box["widget"])
        glayout.addLayout(price_row)

        # Num results (Tradera/eBay only)
        self.results_label = QLabel("")
        self.results_label.setStyleSheet("color: gray; font-size: 11px;")
        self.results_label.setVisible(False)
        glayout.addWidget(self.results_label)

        # Buttons
        btn_row = QHBoxLayout()

        self.analysis_btn = QPushButton("Analysis…")
        self.analysis_btn.setEnabled(False)
        self.analysis_btn.setToolTip("Read the agent's full pricing analysis")
        self.analysis_btn.clicked.connect(self._on_analysis)
        btn_row.addWidget(self.analysis_btn)

        btn_row.addStretch()

        self.refresh_btn = QPushButton("Refresh Price")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.clicked.connect(self._on_refresh)
        btn_row.addWidget(self.refresh_btn)

        glayout.addLayout(btn_row)
        layout.addWidget(group)

    @staticmethod
    def _make_price_col(header: str) -> dict:
        """Return a dict with 'widget', 'header_lbl', 'value_lbl'."""
        col = QWidget()
        col_layout = QVBoxLayout(col)
        col_layout.setContentsMargins(4, 4, 4, 4)
        col_layout.setSpacing(2)

        h = QLabel(header)
        h.setAlignment(Qt.AlignCenter)
        h.setStyleSheet("color: gray; font-size: 11px;")

        v = QLabel("-")
        v.setAlignment(Qt.AlignCenter)
        v.setStyleSheet("font-size: 15px; font-weight: bold;")

        col_layout.addWidget(h)
        col_layout.addWidget(v)
        return {"widget": col, "header_lbl": h, "value_lbl": v}

    def update_for_item(self, item_id: int):
        self._current_item_id = item_id
        self.refresh_btn.setEnabled(True)
        price = get_latest_price(self.conn, item_id)
        if price:
            self._show_price(price)
        else:
            self._show_empty()

    def _show_price(self, price: PriceRecord):
        is_claude = price.source == "claude"

        # Source label
        source_name = {"claude": "Claude AI", "tradera": "Tradera", "ebay": "eBay"}.get(
            price.source, price.source.capitalize()
        )
        self.source_label.setText(f"Source: {source_name}")

        # Date
        self.fetched_label.setText(
            f"checked {price.fetched_at}" if price.fetched_at else ""
        )

        # Middle column label: "Median" for Claude, "Average" for others
        self._mid_box["header_lbl"].setText("Median" if is_claude else "Average")

        # Populate values
        cur = price.currency or "SEK"
        self._low_box["value_lbl"].setText(
            f"{int(price.lowest_price)} {cur}" if price.lowest_price is not None else "-"
        )
        self._mid_box["value_lbl"].setText(
            f"{int(price.avg_price)} {cur}" if price.avg_price is not None else "-"
        )
        self._high_box["value_lbl"].setText(
            f"{int(price.highest_price)} {cur}" if price.highest_price is not None else "-"
        )

        # Results count (Tradera/eBay only)
        if not is_claude and price.num_results:
            self.results_label.setText(f"Based on {price.num_results} listings")
            self.results_label.setVisible(True)
        else:
            self.results_label.setVisible(False)

        # Analysis button
        self._current_notes = price.notes or ""
        self.analysis_btn.setEnabled(bool(self._current_notes))

    def _show_empty(self):
        self.source_label.setText("Source: -")
        self.fetched_label.setText("")
        self._mid_box["header_lbl"].setText("Median")
        for box in (self._low_box, self._mid_box, self._high_box):
            box["value_lbl"].setText("-")
        self.results_label.setVisible(False)
        self._current_notes = ""
        self.analysis_btn.setEnabled(False)

    def clear(self):
        self._current_item_id = None
        self.refresh_btn.setEnabled(False)
        self._show_empty()

    def _on_refresh(self):
        if self._current_item_id is not None:
            self.refresh_requested.emit(self._current_item_id)

    def _on_analysis(self):
        if not self._current_notes:
            return
        dlg = AnalysisDialog(self._current_notes, parent=self)
        dlg.exec()


class AnalysisDialog(QDialog):
    """Displays the Claude agent's full markdown price analysis."""

    def __init__(self, markdown_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Price Analysis")
        self.setMinimumSize(640, 480)
        self.resize(700, 540)

        layout = QVBoxLayout(self)

        browser = QTextBrowser()
        browser.setOpenLinks(False)
        browser.anchorClicked.connect(
            lambda url: QDesktopServices.openUrl(url)
        )
        try:
            browser.document().setMarkdown(markdown_text)
        except Exception:
            browser.setPlainText(markdown_text)
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
