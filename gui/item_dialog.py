import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QCheckBox,
)

from db.database import (
    add_image, add_item, delete_image, get_all_platforms,
    get_images_for_item, set_primary_image, update_item,
)
from db.models import Item, ItemImage

IMAGES_DIR = Path(__file__).parent.parent / "images"

CONDITIONS = ["", "Loose", "CIB", "Sealed", "Boxed (no manual)", "Fair", "Good", "Mint"]


class ItemDialog(QDialog):
    """Dialog for adding or editing a collection item."""

    def __init__(self, conn: sqlite3.Connection, item: Optional[Item] = None,
                 parent=None):
        super().__init__(parent)
        self.conn = conn
        self.item = item
        self._pending_images: list[str] = []  # paths of newly added images
        self._deleted_image_ids: list[int] = []

        self.setWindowTitle("Edit Item" if item else "Add Item")
        self.setMinimumWidth(500)
        self._build_ui()
        if item:
            self._populate(item)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.name_edit = QLineEdit()
        form.addRow("Name:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["game", "console"])
        form.addRow("Type:", self.type_combo)

        self.platform_combo = QComboBox()
        self.platform_combo.setEditable(True)
        platforms = get_all_platforms(self.conn)
        for p in platforms:
            self.platform_combo.addItem(p.name)
        form.addRow("Platform:", self.platform_combo)

        self.condition_combo = QComboBox()
        self.condition_combo.addItems(CONDITIONS)
        form.addRow("Condition:", self.condition_combo)

        self.for_sale_check = QCheckBox("Mark for sale")
        form.addRow("For Sale:", self.for_sale_check)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setMaximumHeight(100)
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        # Image management section
        img_label = QLabel("Images:")
        img_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(img_label)

        img_layout = QHBoxLayout()
        self.image_list = QListWidget()
        self.image_list.setMaximumHeight(120)
        img_layout.addWidget(self.image_list)

        btn_layout = QVBoxLayout()
        self.add_img_btn = QPushButton("Add...")
        self.add_img_btn.clicked.connect(self._add_images)
        btn_layout.addWidget(self.add_img_btn)

        self.remove_img_btn = QPushButton("Remove")
        self.remove_img_btn.clicked.connect(self._remove_image)
        btn_layout.addWidget(self.remove_img_btn)

        self.primary_img_btn = QPushButton("Set Primary")
        self.primary_img_btn.clicked.connect(self._set_primary)
        btn_layout.addWidget(self.primary_img_btn)

        btn_layout.addStretch()
        img_layout.addLayout(btn_layout)
        layout.addLayout(img_layout)

        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate(self, item: Item):
        self.name_edit.setText(item.name)
        self.type_combo.setCurrentText(item.type)
        self.platform_combo.setCurrentText(item.platform)
        if item.condition:
            idx = self.condition_combo.findText(item.condition)
            if idx >= 0:
                self.condition_combo.setCurrentIndex(idx)
            else:
                self.condition_combo.setEditText(item.condition)
        self.for_sale_check.setChecked(item.for_sale)
        self.notes_edit.setPlainText(item.notes or "")

        images = get_images_for_item(self.conn, item.id)
        for img in images:
            li = QListWidgetItem()
            label = img.image_path
            if img.is_primary:
                label += "  [PRIMARY]"
            li.setText(label)
            li.setData(Qt.UserRole, img)
            self.image_list.addItem(li)

    def _add_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)",
        )
        for f in files:
            self._pending_images.append(f)
            li = QListWidgetItem()
            li.setText(Path(f).name + "  [NEW]")
            li.setData(Qt.UserRole, f)  # store path as string for new images
            self.image_list.addItem(li)

    def _remove_image(self):
        current = self.image_list.currentItem()
        if not current:
            return
        data = current.data(Qt.UserRole)
        if isinstance(data, ItemImage):
            self._deleted_image_ids.append(data.id)
        elif isinstance(data, str) and data in self._pending_images:
            self._pending_images.remove(data)
        self.image_list.takeItem(self.image_list.row(current))

    def _set_primary(self):
        current = self.image_list.currentItem()
        if not current:
            return
        # Update labels
        for i in range(self.image_list.count()):
            li = self.image_list.item(i)
            text = li.text().replace("  [PRIMARY]", "")
            li.setText(text)
        text = current.text().replace("  [NEW]", "")
        current.setText(text + "  [PRIMARY]")

        data = current.data(Qt.UserRole)
        if isinstance(data, ItemImage) and self.item:
            set_primary_image(self.conn, self.item.id, data.id)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        platform = self.platform_combo.currentText().strip()
        if not platform:
            QMessageBox.warning(self, "Validation", "Platform is required.")
            return

        if self.item:
            self.item.name = name
            self.item.type = self.type_combo.currentText()
            self.item.platform = platform
            self.item.condition = self.condition_combo.currentText()
            self.item.for_sale = self.for_sale_check.isChecked()
            self.item.notes = self.notes_edit.toPlainText()
            update_item(self.conn, self.item)
        else:
            self.item = Item(
                name=name,
                type=self.type_combo.currentText(),
                platform=platform,
                condition=self.condition_combo.currentText(),
                for_sale=self.for_sale_check.isChecked(),
                notes=self.notes_edit.toPlainText(),
            )
            self.item.id = add_item(self.conn, self.item)

        # Process deleted images
        for img_id in self._deleted_image_ids:
            delete_image(self.conn, img_id)

        # Process new images
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        for src_path in self._pending_images:
            src = Path(src_path)
            ext = src.suffix
            unique_name = f"{uuid.uuid4().hex}{ext}"
            dest = IMAGES_DIR / unique_name
            shutil.copy2(src, dest)
            is_first = len(get_images_for_item(self.conn, self.item.id)) == 0
            add_image(self.conn, ItemImage(
                item_id=self.item.id,
                image_path=unique_name,
                is_primary=is_first,
            ))

        self.accept()
