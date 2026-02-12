import sqlite3

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
    QApplication,
)

from db.models import Item
from export.listing_export import format_bulk_listing, format_csv_listing, format_single_listing


class ExportDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, items: list[Item], parent=None):
        super().__init__(parent)
        self.conn = conn
        self.items = items
        self.setWindowTitle(f"Export {len(items)} Item(s)")
        self.setMinimumSize(600, 500)
        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel(f"Exporting {len(self.items)} item(s)")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header)

        opts_layout = QHBoxLayout()
        opts_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Listing Text", "CSV"])
        self.format_combo.currentIndexChanged.connect(self._update_preview)
        opts_layout.addWidget(self.format_combo)

        self.include_images_check = QCheckBox("Include image paths")
        self.include_images_check.setChecked(True)
        self.include_images_check.stateChanged.connect(self._update_preview)
        opts_layout.addWidget(self.include_images_check)
        opts_layout.addStretch()
        layout.addLayout(opts_layout)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview)

        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(copy_btn)
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _update_preview(self):
        fmt = self.format_combo.currentText()
        include_images = self.include_images_check.isChecked()

        if fmt == "CSV":
            text = format_csv_listing(self.conn, self.items)
        else:
            text = format_bulk_listing(self.conn, self.items, include_images)

        self.preview.setPlainText(text)

    def _copy_to_clipboard(self):
        text = self.preview.toPlainText()
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Copied", "Listing text copied to clipboard.")
