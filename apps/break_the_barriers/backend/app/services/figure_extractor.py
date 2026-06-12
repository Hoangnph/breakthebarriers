"""Crop figure (picture) regions from the page raster into standalone PNGs so the
text-layer renderer can place real images instead of empty <img src="">."""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)


def crop_figure(pil_image, bbox_pt, scale_x: float, scale_y: float,
                output_dir: str, doc_id: str, page_no: int, idx: int) -> str:
    """Crop bbox (in page points) from pil_image (raster px) -> PNG.
    Returns filename only (e.g. 'd-1-fig1.png'). Clamps to image bounds."""
    os.makedirs(output_dir, exist_ok=True)
    l, t, w, h = bbox_pt
    px_l = int(round(l * scale_x)); px_t = int(round(t * scale_y))
    px_r = int(round((l + w) * scale_x)); px_b = int(round((t + h) * scale_y))
    iw, ih = pil_image.size
    px_l = max(0, min(px_l, iw - 1)); px_r = max(px_l + 1, min(px_r, iw))
    px_t = max(0, min(px_t, ih - 1)); px_b = max(px_t + 1, min(px_b, ih))
    crop = pil_image.convert("RGB").crop((px_l, px_t, px_r, px_b))
    filename = f"{doc_id}-{page_no}-fig{idx}.png"
    crop.save(os.path.join(output_dir, filename), "PNG")
    return filename
