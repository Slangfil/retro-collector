#!/usr/bin/env python3
"""Retro Game Collection Manager — entry point."""

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from db.database import get_connection, init_db
from gui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

DARK_STYLE = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 13px;
}
QMainWindow {
    background-color: #1e1e2e;
}
QTableView {
    background-color: #181825;
    alternate-background-color: #1e1e2e;
    gridline-color: #313244;
    selection-background-color: #45475a;
    selection-color: #cdd6f4;
    border: 1px solid #313244;
}
QTableView::item {
    padding: 4px;
}
QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    padding: 6px;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
}
QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 6px 16px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #585b70;
}
QPushButton:pressed {
    background-color: #6c7086;
}
QPushButton:disabled {
    background-color: #313244;
    color: #585b70;
}
QLineEdit, QComboBox, QPlainTextEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
    border-color: #89b4fa;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
    border: 1px solid #45475a;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 16px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #89b4fa;
}
QLabel {
    background: transparent;
}
QScrollArea {
    border: none;
}
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
}
QMenu {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
}
QMenu::item:selected {
    background-color: #45475a;
}
QSplitter::handle {
    background-color: #313244;
    width: 2px;
}
QCheckBox {
    background: transparent;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #585b70;
    border-radius: 3px;
    background-color: #313244;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}
QListWidget {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #45475a;
}
QMessageBox {
    background-color: #1e1e2e;
}
QDialogButtonBox QPushButton {
    min-width: 80px;
}
"""


def main():
    # Ensure images dir exists
    (Path(__file__).parent / "images").mkdir(exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName("Retro Collector")
    app.setStyleSheet(DARK_STYLE)

    conn = get_connection()
    init_db(conn)

    window = MainWindow(conn)
    window.show()

    ret = app.exec()
    conn.close()
    sys.exit(ret)


if __name__ == "__main__":
    main()
