"""QThread worker for running game detection off the main thread.

Follows the PriceLookupWorker pattern from main_window.py.
Creates the GameDetector (and thus EasyOCR model) inside run() so
everything lives on the worker thread.
"""

from PySide6.QtCore import QThread, Signal


class DetectionWorker(QThread):
    """Runs OCR + fuzzy matching on a batch of images."""

    progress = Signal(int, int, str)   # (current, total, filename)
    model_loading = Signal()
    model_loaded = Signal()
    finished = Signal(list)            # list[DetectionResult]
    error = Signal(str)

    def __init__(self, image_paths: list[str]):
        super().__init__()
        self.image_paths = image_paths

    def run(self):
        try:
            self.model_loading.emit()
            from services.game_detector import GameDetector
            detector = GameDetector()
            # Force model load so we can signal when it's ready
            detector._ensure_reader()
            self.model_loaded.emit()

            results = detector.detect_batch(
                self.image_paths,
                progress_callback=self._on_progress,
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, current: int, total: int, filename: str):
        self.progress.emit(current, total, filename)
