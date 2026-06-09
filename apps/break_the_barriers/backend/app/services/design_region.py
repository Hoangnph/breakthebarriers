"""Detect composite design regions (e.g. chat: avatar icons interleaved with text)
that must render as one faithful raster crop, not decomposed into scattered figures +
reflowed text — and infer per-figure horizontal alignment. Pure geometry; the actual
cropping/IO happens in the caller (extractor / backfill). bbox = [x0, y0, w, h] pts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Set, Tuple

from backend.app.services.figure_grouper import cluster_figures  # noqa: F401 (used later)

_ICON_MAX_FRAC = 0.15      # icon: small in BOTH dims relative to the page


def infer_figure_align(bbox, page_w: float, tol_frac: float = 0.08) -> str:
    """Infer a figure's horizontal alignment from its left/right margins on the page.
    `center` when margins are near-equal; `right` when clearly pushed right; else left."""
    if not page_w:
        return "left"
    left = bbox[0]
    right = page_w - (bbox[0] + bbox[2])
    if left <= 0 or right <= 0:
        return "left"
    if abs(left - right) <= tol_frac * page_w:
        return "center"
    if left > 2 * right:
        return "right"
    return "left"
