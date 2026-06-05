"""Page eligibility labels for background reconstruction (#0).

Pure decision logic: given area ratios + per-figure photo/diagram labels,
decide whether a page is plain `text`, must-`preserve` (diagram/chart/table or
anything uncertain), or `regenerable` (image-dominant, low-text, all photos).
Any doubt resolves to `preserve` — a chart must never become regenerable."""
from __future__ import annotations
from typing import List


def classify_page(text_ratio: float, fig_ratio: float, figure_labels: List[str],
                  *, has_table: bool, bg_is_photo: bool,
                  text_max: float = 0.30, fig_min: float = 0.15,
                  text_dominant_min: float = 0.15) -> str:
    has_image = bg_is_photo or fig_ratio >= fig_min or bool(figure_labels)
    if not has_image and text_ratio > 0 and not has_table:
        return "text"
    # Text-dominant page (text covers >= figures, no table, no photo bg): render as
    # text so the body is clean; figures are still cropped & preserved by the renderer.
    if (not bg_is_photo and text_ratio >= text_dominant_min and text_ratio >= fig_ratio
            and not has_table):
        return "text"
    if has_table or any(lbl in ("diagram", "uncertain") for lbl in figure_labels):
        return "preserve"
    if text_ratio < text_max and has_image and all(lbl == "photo" for lbl in figure_labels):
        return "regenerable"
    return "preserve"


def detect_cover(page_index: int, total_pages: int,
                 *, text_ratio: float, fig_ratio: float, bg_is_photo: bool,
                 cover_text_max: float = 0.35, fig_min: float = 0.15) -> str:
    image_like = bg_is_photo or fig_ratio >= fig_min
    if not image_like or text_ratio >= cover_text_max:
        return "none"
    if page_index == 0:
        return "front"
    if page_index == total_pages - 1:
        return "back"
    return "none"
