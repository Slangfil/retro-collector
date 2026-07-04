"""Find and remove duplicate items that share identical image files."""

import hashlib
import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from db.database import delete_item, get_images_for_item

IMAGES_DIR = Path(__file__).parent.parent / "images"


def _hash_file(path: Path) -> str | None:
    try:
        h = hashlib.md5(usedforsecurity=False)
        with open(path, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    except OSError:
        return None


def find_duplicate_groups(conn: sqlite3.Connection, images_dir: Path) -> list[list[dict]]:
    """Return groups of items sharing an identical image, sorted oldest-first.

    Each dict: {item_id, name, platform, condition, image_path (Path)}.
    The first entry in each group is the keeper (lowest item_id).
    """
    rows = conn.execute("""
        SELECT ii.item_id, ii.image_path, i.name, i.platform, i.condition
        FROM item_images ii
        JOIN items i ON ii.item_id = i.id
        ORDER BY ii.item_id ASC
    """).fetchall()

    seen_items: set[int] = set()
    hash_to_group: dict[str, list[dict]] = {}

    for row in rows:
        item_id = row["item_id"]
        if item_id in seen_items:
            continue  # one image per item is enough for comparison
        seen_items.add(item_id)

        path = images_dir / row["image_path"]
        h = _hash_file(path)
        if h is None:
            continue

        entry = {
            "item_id": item_id,
            "name": row["name"],
            "platform": row["platform"] or "",
            "condition": row["condition"] or "",
            "image_path": path,
        }
        hash_to_group.setdefault(h, []).append(entry)

    return [g for g in hash_to_group.values() if len(g) > 1]


class DedupDialog(QDialog):
    """Shows duplicate items (same image content) for review before deletion."""

    COL_THUMB = 0
    COL_NAME = 1
    COL_PLATFORM = 2
    COL_DUP_OF = 3
    COL_DELETE = 4

    def __init__(self, conn: sqlite3.Connection, groups: list[list[dict]], parent=None):
        super().__init__(parent)
        self.conn = conn
        self._deleted = 0

        # Build flat list of duplicates-to-delete (all but the first in each group)
        self._candidates: list[dict] = []
        for group in groups:
            keeper = group[0]
            for dup in group[1:]:
                self._candidates.append({**dup, "keeper_name": keeper["name"]})

        total_groups = len(groups)
        self.setWindowTitle("Remove Duplicate Items")
        self.setMinimumSize(820, 500)
        self.resize(900, 560)
        self._build_ui(total_groups)

    def _build_ui(self, total_groups: int):
        layout = QVBoxLayout(self)

        info = QLabel(
            f"Found <b>{total_groups} group(s)</b> of identical images — "
            f"<b>{len(self._candidates)} duplicate(s)</b> shown below. "
            "The oldest import in each group is kept automatically. "
            "Uncheck anything you want to keep, then click Delete Checked."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["", "Name", "Platform", "Same image as", "Delete"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(62)
        self.table.setColumnWidth(self.COL_THUMB, 72)
        self.table.setColumnWidth(self.COL_DELETE, 62)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_PLATFORM, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_DUP_OF, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self._populate()

        sel_row = QHBoxLayout()
        check_all_btn = QPushButton("Check All")
        check_all_btn.clicked.connect(lambda: self._set_all(True))
        sel_row.addWidget(check_all_btn)
        uncheck_all_btn = QPushButton("Uncheck All")
        uncheck_all_btn.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(uncheck_all_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.delete_btn = QPushButton()
        self.delete_btn.clicked.connect(self._on_delete)
        bottom.addWidget(self.delete_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)

        self._refresh_button()

    def _populate(self):
        self.table.setRowCount(len(self._candidates))
        for row, c in enumerate(self._candidates):
            thumb = QLabel()
            thumb.setAlignment(Qt.AlignCenter)
            pm = QPixmap(str(c["image_path"])).scaled(
                62, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            thumb.setPixmap(pm if not pm.isNull() else QPixmap())
            if pm.isNull():
                thumb.setText("?")
            self.table.setCellWidget(row, self.COL_THUMB, thumb)

            self.table.setItem(row, self.COL_NAME, QTableWidgetItem(c["name"]))
            self.table.setItem(row, self.COL_PLATFORM, QTableWidgetItem(c["platform"] or "-"))
            self.table.setItem(row, self.COL_DUP_OF, QTableWidgetItem(c["keeper_name"]))

            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb_layout.setAlignment(Qt.AlignCenter)
            cb = QCheckBox()
            cb.setChecked(True)
            cb.stateChanged.connect(self._refresh_button)
            cb_layout.addWidget(cb)
            self.table.setCellWidget(row, self.COL_DELETE, cb_widget)

    def _checked_rows(self) -> list[int]:
        return [
            r for r in range(self.table.rowCount())
            if (w := self.table.cellWidget(r, self.COL_DELETE))
            and w.findChild(QCheckBox).isChecked()
        ]

    def _refresh_button(self):
        n = len(self._checked_rows())
        self.delete_btn.setText(f"Delete Checked ({n})")
        self.delete_btn.setEnabled(n > 0)

    def _set_all(self, checked: bool):
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, self.COL_DELETE)
            if w:
                w.findChild(QCheckBox).setChecked(checked)

    def _on_delete(self):
        rows = self._checked_rows()
        for row in rows:
            c = self._candidates[row]
            # Collect image files before the cascade delete removes the DB records
            images = get_images_for_item(self.conn, c["item_id"])
            delete_item(self.conn, c["item_id"])  # cascades item_images
            for img in images:
                p = IMAGES_DIR / img.image_path
                p.unlink(missing_ok=True)
        self._deleted = len(rows)
        self.accept()

    @property
    def deleted_count(self) -> int:
        return self._deleted
