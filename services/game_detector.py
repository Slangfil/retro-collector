"""Game detection from photos using OCR and fuzzy matching.

Pipeline: preprocess image → EasyOCR → platform detection → fuzzy match → confidence score.
No Qt or DB dependencies — pure service module.
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class DetectionResult:
    image_path: str
    detected_name: str = ""
    detected_platform: str = ""
    confidence: float = 0.0
    raw_ocr_text: str = ""
    ocr_fragments: list[str] = field(default_factory=list)
    alternate_matches: list[tuple[str, str, float]] = field(default_factory=list)
    # [(name, platform, score), ...]


def _normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace, remove punctuation."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class GameDatabase:
    """Loads the bundled game database and provides fuzzy search."""

    def __init__(self, db_path: Path | None = None):
        path = db_path or (DATA_DIR / "game_database.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.platforms: dict = data["platforms"]

        # Flat search index: [(normalized_name, platform, canonical_name), ...]
        self.search_index: list[tuple[str, str, str]] = []
        for platform, info in self.platforms.items():
            for game in info["games"]:
                canonical = game["name"]
                self.search_index.append((_normalize(canonical), platform, canonical))
                for alt in game.get("alt_names", []):
                    if alt:
                        self.search_index.append((_normalize(alt), platform, canonical))

        # Platform cue map: normalized_cue → (platform, cue_length)
        self.platform_cues: list[tuple[str, str, int]] = []
        for platform, info in self.platforms.items():
            for cue in info.get("text_cues", []):
                norm = _normalize(cue)
                self.platform_cues.append((norm, platform, len(norm)))
        # Sort by cue length descending so longer/more specific cues match first
        self.platform_cues.sort(key=lambda x: -x[2])

    def detect_platform(self, ocr_text: str) -> list[tuple[str, float]]:
        """Score platforms by text cue matches. Returns [(platform, score), ...] sorted desc."""
        norm = _normalize(ocr_text)
        scores: dict[str, float] = {}
        for cue, platform, length in self.platform_cues:
            if cue in norm:
                # Longer cues are weighted heavier (more specific)
                weight = length / 5.0
                scores[platform] = scores.get(platform, 0) + weight
        result = sorted(scores.items(), key=lambda x: -x[1])
        return result

    def match_game(
        self, ocr_text: str, fragments: list[str], platform_hint: str = ""
    ) -> list[tuple[str, str, float]]:
        """Fuzzy-match OCR text against game database.

        Returns [(canonical_name, platform, score), ...] sorted by score desc.
        """
        from rapidfuzz import fuzz, process

        norm_text = _normalize(ocr_text)
        # Also try each fragment individually
        norm_fragments = [_normalize(f) for f in fragments if len(f.strip()) > 2]

        # Build candidates, optionally filtered by platform.
        # Skip very short names (< 4 chars) — they cause false 100% matches
        # with token_set_ratio (e.g. "C&C" → "c c" matches any text containing "c").
        if platform_hint:
            candidates = [
                (n, p, c) for n, p, c in self.search_index
                if p == platform_hint and len(n) >= 4
            ]
        else:
            candidates = [
                (n, p, c) for n, p, c in self.search_index if len(n) >= 4
            ]

        if not candidates:
            candidates = [(n, p, c) for n, p, c in self.search_index if len(n) >= 4]

        choices = [entry[0] for entry in candidates]
        if not choices:
            return []

        # Score with both token_set_ratio (noise-tolerant) and token_sort_ratio
        # (stricter), then blend. token_set_ratio alone gives 100% to anything
        # whose tokens are a subset of the OCR text.
        results_set = process.extract(
            norm_text, choices, scorer=fuzz.token_set_ratio, limit=15
        )
        results_sort = process.extract(
            norm_text, choices, scorer=fuzz.token_sort_ratio, limit=15
        )

        # Also match individual fragments (good for when the game name is one
        # clean fragment among noise)
        for frag in norm_fragments:
            if len(frag) < 4:
                continue
            frag_set = process.extract(
                frag, choices, scorer=fuzz.token_set_ratio, limit=5
            )
            frag_sort = process.extract(
                frag, choices, scorer=fuzz.token_sort_ratio, limit=5
            )
            results_set.extend(frag_set)
            results_sort.extend(frag_sort)

        # Collect best score per index for each scorer
        best_set: dict[int, float] = {}
        for _, score, idx in results_set:
            if idx not in best_set or score > best_set[idx]:
                best_set[idx] = score

        best_sort: dict[int, float] = {}
        for _, score, idx in results_sort:
            if idx not in best_sort or score > best_sort[idx]:
                best_sort[idx] = score

        # Blend: 40% token_set + 60% token_sort. This keeps noise tolerance
        # but prevents short-name false positives from dominating.
        all_indices = set(best_set) | set(best_sort)
        blended: dict[int, float] = {}
        for idx in all_indices:
            s_set = best_set.get(idx, 0)
            s_sort = best_sort.get(idx, 0)
            blended[idx] = 0.4 * s_set + 0.6 * s_sort

        # Map back to (canonical_name, platform, score)
        output: list[tuple[str, str, float]] = []
        seen = set()
        for idx, score in sorted(blended.items(), key=lambda x: -x[1]):
            _, platform, canonical = candidates[idx]
            key = (canonical, platform)
            if key not in seen:
                seen.add(key)
                output.append((canonical, platform, score / 100.0))

        return output[:10]


def preprocess_image(path: str) -> list[np.ndarray]:
    """Preprocess image for OCR. Returns list of variants to try."""
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Could not read image: {path}")

    variants = []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Upscale small images to minimum 800px on shortest side
    h, w = gray.shape[:2]
    min_dim = min(h, w)
    if min_dim < 800:
        scale = 800 / min_dim
        gray = cv2.resize(
            gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )

    # Variant 1: CLAHE contrast enhancement (good for faded labels)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    variants.append(enhanced)

    # Variant 2: plain grayscale as fallback
    variants.append(gray)

    return variants


class GameDetector:
    """Full detection pipeline: preprocess → OCR → platform detect → fuzzy match."""

    def __init__(self):
        self._reader = None
        self._db = GameDatabase()

    def _ensure_reader(self):
        if self._reader is None:
            import easyocr
            log.info("Loading EasyOCR model (first use may download ~100MB)...")
            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            log.info("EasyOCR model loaded.")

    def detect_game(self, image_path: str) -> DetectionResult:
        """Full detection pipeline for a single image."""
        self._ensure_reader()

        result = DetectionResult(image_path=image_path)

        try:
            variants = preprocess_image(image_path)
        except ValueError as e:
            log.warning("Preprocess failed for %s: %s", image_path, e)
            return result

        # Run OCR on each variant, pick the one with most text
        best_texts: list[str] = []
        best_raw = ""
        for variant in variants:
            ocr_results = self._reader.readtext(variant, detail=1)
            texts = [text for (_, text, conf) in ocr_results if conf > 0.15]
            raw = " ".join(texts)
            if len(raw) > len(best_raw):
                best_raw = raw
                best_texts = texts

        result.raw_ocr_text = best_raw
        result.ocr_fragments = best_texts

        if not best_raw.strip():
            return result

        # Detect platform
        platform_scores = self._db.detect_platform(best_raw)
        platform_hint = platform_scores[0][0] if platform_scores else ""

        # Fuzzy match
        matches = self._db.match_game(best_raw, best_texts, platform_hint)

        if matches:
            top_name, top_platform, top_score = matches[0]
            result.detected_name = top_name
            result.detected_platform = top_platform
            result.confidence = top_score
            result.alternate_matches = matches[1:6]
        elif platform_hint:
            # No game match but we detected a platform
            result.detected_platform = platform_hint

        return result

    def detect_batch(
        self,
        image_paths: list[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[DetectionResult]:
        """Run detection on multiple images with progress reporting."""
        results = []
        total = len(image_paths)
        for i, path in enumerate(image_paths):
            if progress_callback:
                progress_callback(i, total, Path(path).name)
            try:
                result = self.detect_game(path)
            except Exception as e:
                log.error("Detection failed for %s: %s", path, e)
                result = DetectionResult(image_path=path)
            results.append(result)

        if progress_callback:
            progress_callback(total, total, "Done")
        return results
