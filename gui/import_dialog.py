"""Mass import dialog: select photos, detect games via OCR, review and save."""

import shutil
import sqlite3
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QAbstractItemView,
)

from db.database import add_image, add_item, get_all_platforms
from db.models import Item, ItemImage
from gui.item_dialog import CONDITIONS

IMAGES_DIR = Path(__file__).parent.parent / "images"

# Catppuccin-style colors for confidence
_GREEN = QColor(166, 227, 161)   # a6e3a1
_YELLOW = QColor(249, 226, 175)  # f9e2af
_RED = QColor(243, 139, 168)     # f38ba8
_DIM = QColor(88, 91, 112)       # 585b70


class ImportDialog(QDialog):
    """Dialog for batch-importing games from photos with AI detection."""

    items_imported = Signal()

    # Column indices
    COL_THUMB = 0
    COL_NAME = 1
    COL_PLATFORM = 2
    COL_CONDITION = 3
    COL_CONFIDENCE = 4
    COL_INCLUDE = 5

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Import Photos")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)

        self._results = []     # list[DetectionResult]
        self._image_paths = [] # list[str]
        self._worker = None
        self._detail_row = -1  # currently displayed row in detail panel

        self._platforms = [p.name for p in get_all_platforms(conn)]
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Top bar: buttons + status
        top = QHBoxLayout()
        self.select_btn = QPushButton("Select Photos...")
        self.select_btn.clicked.connect(self._on_select_photos)
        top.addWidget(self.select_btn)

        self.detect_btn = QPushButton("Detect All")
        self.detect_btn.setEnabled(False)
        self.detect_btn.clicked.connect(self._on_detect)
        top.addWidget(self.detect_btn)

        self.status_label = QLabel("No photos loaded")
        top.addWidget(self.status_label, 1)
        layout.addLayout(top)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)

        prog_layout = QHBoxLayout()
        prog_layout.addWidget(self.progress_bar, 1)
        prog_layout.addWidget(self.progress_label)
        layout.addLayout(prog_layout)

        # Splitter: table on top, detail panel on bottom
        splitter = QSplitter(Qt.Vertical)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["", "Name", "Platform", "Condition", "Conf.", "Include"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setColumnWidth(self.COL_THUMB, 60)
        self.table.setColumnWidth(self.COL_CONFIDENCE, 50)
        self.table.setColumnWidth(self.COL_INCLUDE, 55)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_PLATFORM, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_CONDITION, QHeaderView.ResizeToContents)
        self.table.currentCellChanged.connect(self._on_row_changed)
        splitter.addWidget(self.table)

        # Detail panel — image on the left, AI info on the right
        detail_widget = QWidget()
        detail_outer = QHBoxLayout(detail_widget)
        detail_outer.setContentsMargins(4, 4, 4, 4)
        detail_outer.setSpacing(8)

        # Left: large image preview (click to zoom)
        self.detail_image = QLabel("No image")
        self.detail_image.setAlignment(Qt.AlignCenter)
        self.detail_image.setFixedSize(180, 160)
        self.detail_image.setStyleSheet(
            "background: #1e1e2e; border: 1px solid #45475a; border-radius: 4px;"
            "color: #585b70;"
        )
        self.detail_image.setCursor(QCursor(Qt.PointingHandCursor))
        self.detail_image.mousePressEvent = self._on_preview_click
        self._detail_image_path: str = ""
        detail_outer.addWidget(self.detail_image)

        # Right: AI response + alternatives
        info_widget = QWidget()
        detail_layout = QVBoxLayout(info_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        self.ocr_label = QLabel("AI response:")
        self.ocr_label.setStyleSheet("font-weight: bold;")
        detail_layout.addWidget(self.ocr_label)

        self.ocr_text = QTextEdit()
        self.ocr_text.setReadOnly(True)
        self.ocr_text.setMaximumHeight(60)
        detail_layout.addWidget(self.ocr_text)

        self.alt_label = QLabel("Alternatives:")
        self.alt_label.setStyleSheet("font-weight: bold;")
        detail_layout.addWidget(self.alt_label)

        self.alt_text = QLabel("")
        self.alt_text.setWordWrap(True)
        detail_layout.addWidget(self.alt_text)
        detail_layout.addStretch()

        detail_outer.addWidget(info_widget, 1)

        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # Bottom bar
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.save_btn = QPushButton("Save Selected (0)")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        bottom.addWidget(self.save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)

    # --- Photo selection ---

    def _on_select_photos(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Game Photos", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)",
        )
        if not files:
            return

        self._image_paths = files
        self._results = []
        self._detail_row = -1
        self.table.setRowCount(len(files))

        for row, path in enumerate(files):
            self._setup_row(row, path)

        self.detect_btn.setEnabled(True)
        self.save_btn.setEnabled(False)
        self._update_status()

    def _hook_mouse_press(self, widget, row):
        """Patch mousePressEvent on widget so clicking it shows row details."""
        orig = widget.mousePressEvent

        def patched(event, r=row, o=orig):
            self._show_row_details(r)
            o(event)

        widget.mousePressEvent = patched

    def _setup_row(self, row: int, image_path: str):
        """Set up an empty row with thumbnail and editable widgets."""
        # Thumbnail
        thumb_label = QLabel()
        thumb_label.setAlignment(Qt.AlignCenter)
        pm = QPixmap(image_path).scaled(
            50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        if not pm.isNull():
            thumb_label.setPixmap(pm)
        else:
            thumb_label.setText("?")
        self.table.setCellWidget(row, self.COL_THUMB, thumb_label)

        # Name (editable line edit)
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("(no detection)")
        name_edit.textChanged.connect(self._update_save_count)
        self.table.setCellWidget(row, self.COL_NAME, name_edit)

        # Platform combo
        platform_combo = QComboBox()
        platform_combo.addItem("")
        platform_combo.addItems(self._platforms)
        platform_combo.setEditable(True)
        self.table.setCellWidget(row, self.COL_PLATFORM, platform_combo)

        # Condition combo
        cond_combo = QComboBox()
        cond_combo.addItems(CONDITIONS)
        cond_idx = CONDITIONS.index("Loose") if "Loose" in CONDITIONS else 0
        cond_combo.setCurrentIndex(cond_idx)
        self.table.setCellWidget(row, self.COL_CONDITION, cond_combo)

        # Confidence
        conf_item = QTableWidgetItem("--")
        conf_item.setTextAlignment(Qt.AlignCenter)
        conf_item.setFlags(conf_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, self.COL_CONFIDENCE, conf_item)

        # Include checkbox
        include_widget = QWidget()
        include_layout = QHBoxLayout(include_widget)
        include_layout.setContentsMargins(0, 0, 0, 0)
        include_layout.setAlignment(Qt.AlignCenter)
        cb = QCheckBox()
        cb.stateChanged.connect(self._update_save_count)
        include_layout.addWidget(cb)
        self.table.setCellWidget(row, self.COL_INCLUDE, include_widget)

        # Patch mousePressEvent on every interactive widget so clicking
        # anywhere in the row updates the detail panel. This is more
        # reliable than event filters or currentCellChanged, which don't
        # fire for embedded cell widgets.
        for widget in (thumb_label, name_edit, platform_combo,
                       cond_combo, include_widget, cb):
            self._hook_mouse_press(widget, row)

    # --- Detection ---

    def _on_detect(self):
        if not self._image_paths:
            return

        self.detect_btn.setEnabled(False)
        self.select_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_bar.setMaximum(len(self._image_paths))
        self.progress_bar.setValue(0)
        self.progress_label.setText("Connecting to Claude API...")

        from gui.detection_worker import DetectionWorker
        self._worker = DetectionWorker(self._image_paths)
        self._worker.model_loading.connect(
            lambda: self.progress_label.setText("Connecting to Claude API...")
        )
        self._worker.model_loaded.connect(
            lambda: self.progress_label.setText("Connected. Starting detection...")
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_detection_finished)
        self._worker.error.connect(self._on_detection_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, filename: str):
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"Processing {filename}... ({current}/{total})")

    def _on_detection_finished(self, results):
        self._results = results
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_label.setText("Detection complete")

        for row, result in enumerate(results):
            name_edit = self.table.cellWidget(row, self.COL_NAME)
            platform_combo = self.table.cellWidget(row, self.COL_PLATFORM)
            conf_item = self.table.item(row, self.COL_CONFIDENCE)
            include_widget = self.table.cellWidget(row, self.COL_INCLUDE)
            cb = include_widget.findChild(QCheckBox)

            if result.detected_name:
                name_edit.setText(result.detected_name)
            if result.detected_platform:
                idx = platform_combo.findText(result.detected_platform)
                if idx >= 0:
                    platform_combo.setCurrentIndex(idx)
                else:
                    platform_combo.setEditText(result.detected_platform)

            # Confidence display
            if result.detected_name:
                pct = int(result.confidence * 100)
                conf_item.setText(f"{pct}%")
                if result.confidence >= 0.85:
                    conf_item.setForeground(_GREEN)
                elif result.confidence >= 0.60:
                    conf_item.setForeground(_YELLOW)
                else:
                    conf_item.setForeground(_RED)

                # Auto-check if confidence >= 50%
                cb.setChecked(result.confidence >= 0.50)
            else:
                conf_item.setText("--")
                conf_item.setForeground(_DIM)
                cb.setChecked(False)

        self.detect_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        self._update_save_count()
        self._cleanup_worker()

        detected = sum(1 for r in results if r.detected_name)
        self._update_status(detected)

        # Auto-show details for the first row
        if results:
            self._show_row_details(0)

    def _on_detection_error(self, error: str):
        self.progress_label.setText(f"Error: {error}")
        self.detect_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        self._cleanup_worker()
        QMessageBox.warning(self, "Detection Error", f"Detection failed:\n{error}")

    def _cleanup_worker(self):
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    # --- Row selection / detail panel ---

    def _on_row_changed(self, row, _col, _prev_row, _prev_col):
        self._show_row_details(row)

    def _show_row_details(self, row: int):
        if row < 0 or row >= len(self._results):
            return
        if row == self._detail_row:
            return
        self._detail_row = row

        # Image preview
        if row < len(self._image_paths):
            path = self._image_paths[row]
            self._detail_image_path = path
            pm = QPixmap(path).scaled(
                180, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            if not pm.isNull():
                self.detail_image.setPixmap(pm)
                self.detail_image.setToolTip("Click to zoom")
            else:
                self.detail_image.clear()
                self.detail_image.setText("?")
                self.detail_image.setToolTip("")
        else:
            self.detail_image.clear()
            self.detail_image.setText("No image")
            self._detail_image_path = ""

        result = self._results[row]
        self.ocr_text.setPlainText(result.raw_ocr_text or "(no text detected)")

        if result.alternate_matches:
            parts = []
            for name, platform, score in result.alternate_matches:
                pct = int(score * 100)
                parts.append(f"{name} ({platform}, {pct}%)")
            self.alt_text.setText(" | ".join(parts))
        else:
            self.alt_text.setText("(none)")

    def _on_preview_click(self, _event):
        if not self._detail_image_path:
            return
        dlg = _PhotoZoomDialog(self._detail_image_path, parent=self)
        dlg.exec()

    # --- Save ---

    def _get_checked_count(self) -> int:
        count = 0
        for row in range(self.table.rowCount()):
            include_widget = self.table.cellWidget(row, self.COL_INCLUDE)
            if include_widget:
                cb = include_widget.findChild(QCheckBox)
                name_edit = self.table.cellWidget(row, self.COL_NAME)
                if cb and cb.isChecked() and name_edit and name_edit.text().strip():
                    count += 1
        return count

    def _update_save_count(self):
        count = self._get_checked_count()
        self.save_btn.setText(f"Save Selected ({count})")
        self.save_btn.setEnabled(count > 0)

    def _update_status(self, detected: int = 0):
        total = len(self._image_paths)
        if detected:
            self.status_label.setText(
                f"{total} photos loaded, {detected} detected"
            )
        else:
            self.status_label.setText(f"{total} photos loaded")

    def _on_save(self):
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        saved = 0

        for row in range(self.table.rowCount()):
            include_widget = self.table.cellWidget(row, self.COL_INCLUDE)
            cb = include_widget.findChild(QCheckBox)
            if not cb or not cb.isChecked():
                continue

            name_edit = self.table.cellWidget(row, self.COL_NAME)
            platform_combo = self.table.cellWidget(row, self.COL_PLATFORM)
            cond_combo = self.table.cellWidget(row, self.COL_CONDITION)

            name = name_edit.text().strip()
            platform = platform_combo.currentText().strip()
            if not name:
                continue

            # Create item (follows ItemDialog._on_accept pattern)
            item = Item(
                name=name,
                type="game",
                platform=platform,
                condition=cond_combo.currentText(),
            )
            item_id = add_item(self.conn, item)

            # Copy image with UUID filename
            src = Path(self._image_paths[row])
            ext = src.suffix
            unique_name = f"{uuid.uuid4().hex}{ext}"
            dest = IMAGES_DIR / unique_name
            shutil.copy2(src, dest)
            add_image(self.conn, ItemImage(
                item_id=item_id,
                image_path=unique_name,
                is_primary=True,
            ))
            saved += 1

        if saved:
            self.items_imported.emit()
            QMessageBox.information(
                self, "Import Complete",
                f"Successfully imported {saved} item(s).",
            )
            self.accept()


class _PhotoZoomDialog(QDialog):
    """Full-size photo viewer — click anywhere or press Escape to close."""

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Photo Preview")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        screen = self.screen().availableGeometry()
        max_w = int(screen.width() * 0.85)
        max_h = int(screen.height() * 0.85)

        pm = QPixmap(image_path)
        if not pm.isNull() and (pm.width() > max_w or pm.height() > max_h):
            pm = pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        img_label = QLabel()
        img_label.setAlignment(Qt.AlignCenter)
        if not pm.isNull():
            img_label.setPixmap(pm)
            self.resize(pm.width(), pm.height())
        else:
            img_label.setText("Could not load image")
            self.resize(400, 300)

        scroll = QScrollArea()
        scroll.setWidget(img_label)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.NoFrame)
        layout.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
