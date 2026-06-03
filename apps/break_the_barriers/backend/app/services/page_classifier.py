"""Classify a page as text | image | mixed from text/figure area ratios.
When uncertain, return 'mixed' (safe: keeps the raster)."""
from __future__ import annotations
from typing import List


def _area(boxes: List[List[float]]) -> float:
    return sum(max(0.0, b[2]) * max(0.0, b[3]) for b in boxes)


def classify_kind(page_w: float, page_h: float,
                  block_boxes: List[List[float]], figure_boxes: List[List[float]],
                  *, image_dominant_ratio: float = 0.55,
                  text_min_ratio: float = 0.06,
                  bg_is_photo: bool = False) -> str:
    page_area = max(page_w * page_h, 1.0)
    text_ratio = _area(block_boxes) / page_area
    fig_ratio = _area(figure_boxes) / page_area

    # A photo-like full-bleed background must keep its raster: route image/mixed.
    if bg_is_photo:
        return "mixed" if text_ratio >= text_min_ratio else "image"

    if not block_boxes and not figure_boxes:
        return "mixed"
    if fig_ratio >= image_dominant_ratio and text_ratio < text_min_ratio:
        return "image"
    if fig_ratio >= 0.15 and text_ratio >= text_min_ratio:
        return "mixed"
    if text_ratio >= text_min_ratio:
        return "text"
    return "mixed"
