"""Review dialog: delete image files that are not linked to any collection item."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)


class CleanupDialog(QDialog):
    """Shows unlinked image files for review before deletion.

    These files exist in the images folder but are not referenced by any
    item in the database, so deleting them does not affect any thumbnails.
    """

    COL_THUMB = 0
    COL_FILENAME = 1
    COL_DELETE = 2

    def __init__(self, orphans: list[Path], parent=None):
        super().__init__(parent)
        self.orphans = orphans
        self._deleted = 0
        self.setWindowTitle("Clean Image Folder")
        self.setMinimumSize(600, 440)
        self.resize(660, 500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            f"<b>{len(self.orphans)}</b> image file(s) are not linked to any collection item "
            "and can be safely deleted. Thumbnails used by your collection are not shown here."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["", "Filename", "Delete"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(62)
        self.table.setColumnWidth(self.COL_THUMB, 72)
        self.table.setColumnWidth(self.COL_DELETE, 62)
        self.table.horizontalHeader().setSectionResizeMode(
            self.COL_FILENAME, QHeaderView.Stretch
        )
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
        self.table.setRowCount(len(self.orphans))
        for row, path in enumerate(self.orphans):
            thumb = QLabel()
            thumb.setAlignment(Qt.AlignCenter)
            pm = QPixmap(str(path)).scaled(
                62, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            if not pm.isNull():
                thumb.setPixmap(pm)
            else:
                thumb.setText("?")
            self.table.setCellWidget(row, self.COL_THUMB, thumb)

            self.table.setItem(row, self.COL_FILENAME, QTableWidgetItem(path.name))

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
        for row in self._checked_rows():
            self.orphans[row].unlink(missing_ok=True)
        self._deleted = len(self._checked_rows())
        self.accept()

    @property
    def deleted_count(self) -> int:
        return self._deleted
