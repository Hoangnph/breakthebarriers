"""Detect baked-in text regions inside a figure crop using the tesseract binary
(offline). Returns word bounding boxes in figure pixels; empty list = no text."""
from __future__ import annotations
import os
import shutil
import subprocess
import logging

logger = logging.getLogger(__name__)

_TESSERACT = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"


def detect_text_boxes(crop_path: str, *, min_conf: int = 40,
                      min_h_frac: float = 0.04) -> list:
    """List of (left, top, width, height) px boxes for confident text words.
    Any failure (no tesseract, unreadable image) returns []."""
    try:
        if not os.path.exists(crop_path):
            return []
        from PIL import Image
        height = Image.open(crop_path).height or 1
        proc = subprocess.run(
            [_TESSERACT, crop_path, "stdout", "--psm", "11", "tsv"],
            capture_output=True, text=True, timeout=30)
        boxes = []
        for line in proc.stdout.splitlines()[1:]:   # skip TSV header
            parts = line.split("\t")
            if len(parts) < 12:
                continue
            text = parts[11].strip()
            if not text:
                continue
            try:
                conf = float(parts[10])
                l, t, w, h = (int(parts[6]), int(parts[7]),
                              int(parts[8]), int(parts[9]))
            except ValueError:
                continue
            if conf < min_conf or h < min_h_frac * height:
                continue
            boxes.append((l, t, w, h))
        return boxes
    except Exception as e:
        logger.warning(f"detect_text_boxes failed for {crop_path}: {e}")
        return []
