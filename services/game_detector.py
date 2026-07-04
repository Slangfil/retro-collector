"""Game detection from photos using the Claude vision API."""

import base64
import io
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

_PROMPT = (
    "Identify the video game shown in this image.\n\n"
    "IMPORTANT: First read any text visible on the box, cartridge, or disc — "
    "the printed title is more reliable than art style. "
    "Many game series have subtitles that are easy to miss (e.g. GTA games: "
    "Vice City, San Andreas, Liberty City Stories, Chinatown Wars are all different games "
    "with very different cover art — read the subtitle carefully). "
    "Match the platform printed on the case (PS2, Xbox, etc.) — never assign a platform "
    "the game was not released on.\n\n"
    "Respond with ONLY a JSON object — no markdown fences, no extra text:\n"
    '{"name": "exact game title including subtitle", "platform": "platform name", "confidence": 0.95, '
    '"alternatives": [{"name": "other title", "platform": "platform", "confidence": 0.4}]}\n\n'
    "Platform names: NES, SNES, N64, GameCube, Wii, Wii U, Game Boy, Game Boy Color, GBA, "
    "DS, 3DS, Switch, PlayStation, PS2, PS3, PS4, PS5, PSP, PS Vita, "
    "Sega Master System, Sega Genesis, Sega Saturn, Dreamcast, Game Gear, "
    "Xbox, Xbox 360, Xbox One, PC, Amiga, Atari 2600, Atari 7800, "
    "Commodore 64, TurboGrafx-16, Neo Geo, etc.\n\n"
    'If you cannot identify the game: {"name": "", "platform": "", "confidence": 0.0, "alternatives": []}\n'
    "Include up to 3 alternatives if uncertain. confidence is 0.0–1.0."
)


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


def _load_image_base64(image_path: str) -> tuple[str, str]:
    """Return (base64_data, media_type). Converts non-JPEG/PNG to JPEG via Pillow."""
    from PIL import Image

    ext = Path(image_path).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode(), "image/jpeg"
    if ext == ".png":
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode(), "image/png"
    if ext == ".gif":
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode(), "image/gif"
    if ext == ".webp":
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode(), "image/webp"

    # BMP and anything else: convert to JPEG via Pillow
    img = Image.open(image_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


class GameDetector:
    """Identifies games from photos using the Claude vision API."""

    def __init__(self):
        self._client = None

    def _ensure_reader(self):
        """Initialise the Anthropic client (instant, no model download)."""
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()

    def detect_game(self, image_path: str) -> DetectionResult:
        """Identify the game in a single image via Claude."""
        self._ensure_reader()
        result = DetectionResult(image_path=image_path)

        try:
            image_data, media_type = _load_image_base64(image_path)
        except Exception as e:
            log.warning("Could not read image %s: %s", image_path, e)
            return result

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }],
            )
        except Exception as e:
            log.error("API call failed for %s: %s", image_path, e)
            result.raw_ocr_text = f"API error: {e}"
            return result

        raw = response.content[0].text if response.content else ""
        text = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        result.raw_ocr_text = text  # store clean JSON, not fenced markdown

        try:
            data = json.loads(text)
            result.detected_name = data.get("name", "") or ""
            result.detected_platform = data.get("platform", "") or ""
            result.confidence = float(data.get("confidence", 0.0))
            result.alternate_matches = [
                (
                    alt.get("name", ""),
                    alt.get("platform", ""),
                    float(alt.get("confidence", 0.0)),
                )
                for alt in data.get("alternatives", [])
                if alt.get("name")
            ]
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            log.warning(
                "Could not parse API response for %s: %s\nRaw: %s",
                image_path, e, raw,
            )

        return result

    def detect_batch(
        self,
        image_paths: list[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[DetectionResult]:
        """Run detection on multiple images with optional progress reporting."""
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
