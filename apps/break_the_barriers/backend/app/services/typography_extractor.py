"""Extract real typography (font size/weight/italic/color/align) per text block
using PyMuPDF, mapping PDF font names to coarse family classes.

Pure helpers are unit-tested; extract_page_fonts (PyMuPDF I/O) is covered by the
extractor integration test."""
from __future__ import annotations
import logging
from collections import Counter
from typing import List, Dict, Optional

from backend.app.services.page_model import FontSpec

logger = logging.getLogger(__name__)

_MONO_HINTS = ("mono", "courier", "consol", "menlo", "jetbrains")
_SERIF_HINTS = ("times", "serif", "georgia", "minion", "garamond", "roman")


def classify_font_family(font_name: str) -> str:
    n = (font_name or "").lower()
    if any(h in n for h in _MONO_HINTS):
        return "mono"
    if any(h in n for h in _SERIF_HINTS):
        return "serif"
    return "sans"


def int_color_to_hex(c: int) -> str:
    c = int(c) & 0xFFFFFF
    return f"#{c:06x}"


def is_bold(flags: int) -> bool:
    return bool(int(flags) & (1 << 4))


def is_italic(flags: int) -> bool:
    return bool(int(flags) & (1 << 1))


def iou(a: List[float], b: List[float]) -> float:
    """IoU of two [l, t, w, h] boxes."""
    al, at, aw, ah = a
    bl, bt, bw, bh = b
    ar, ab = al + aw, at + ah
    br, bb = bl + bw, bt + bh
    ix = max(0.0, min(ar, br) - max(al, bl))
    iy = max(0.0, min(ab, bb) - max(at, bt))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def aggregate_font(spans: List[dict], align: str = "left") -> Optional[FontSpec]:
    """Collapse PyMuPDF spans (dicts with size/flags/color/font) into one FontSpec.
    Returns None when there are no spans."""
    if not spans:
        return None
    sizes = Counter(round(float(s.get("size", 0)), 1) for s in spans)
    size = sizes.most_common(1)[0][0]
    bold_votes = sum(1 for s in spans if is_bold(s.get("flags", 0)))
    italic_votes = sum(1 for s in spans if is_italic(s.get("flags", 0)))
    colors = Counter(int(s.get("color", 0)) for s in spans)
    fonts = Counter(str(s.get("font", "")) for s in spans)
    dominant_font = fonts.most_common(1)[0][0]
    return FontSpec(
        size=size,
        weight=700 if bold_votes * 2 >= len(spans) else 400,
        italic=italic_votes * 2 >= len(spans),
        color=int_color_to_hex(colors.most_common(1)[0][0]),
        align=align,
        family_class=classify_font_family(dominant_font),
    )


def detect_align(line_lefts: List[float], block_l: float, block_w: float,
                 tol: float = 2.0) -> str:
    """Infer alignment from where lines start within the block."""
    if not line_lefts:
        return "left"
    block_r = block_l + block_w
    center = block_l + block_w / 2.0
    near_left = sum(1 for x in line_lefts if abs(x - block_l) <= max(tol, block_w * 0.05))
    if near_left * 2 >= len(line_lefts):
        return "left"
    near_center = sum(1 for x in line_lefts if abs(x - center) <= block_w * 0.15)
    if near_center * 2 >= len(line_lefts):
        return "center"
    return "left"


def extract_page_fonts(pdf_path: str, page_no: int,
                       blocks: List[dict], iou_threshold: float = 0.1
                       ) -> Dict[str, FontSpec]:
    """Map span_id -> FontSpec by matching docling blocks against PyMuPDF spans.

    `blocks` are docling blocks: {"span_id", "bbox": [l,t,w,h]} (top-left points).
    Any failure returns {} so the renderer falls back to role-based defaults."""
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF not installed; skipping font extraction")
        return {}
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_no - 1]  # PyMuPDF is 0-indexed
        raw = page.get_text("dict")
        pdf_spans = []
        for blk in raw.get("blocks", []):
            for line in blk.get("lines", []):
                for sp in line.get("spans", []):
                    x0, y0, x1, y1 = sp["bbox"]
                    pdf_spans.append({
                        "box": [x0, y0, x1 - x0, y1 - y0],
                        "left": x0,
                        "size": sp.get("size", 0), "flags": sp.get("flags", 0),
                        "color": sp.get("color", 0), "font": sp.get("font", ""),
                    })
        result: Dict[str, FontSpec] = {}
        for b in blocks:
            matched = [s for s in pdf_spans if iou(b["bbox"], s["box"]) >= iou_threshold]
            if not matched:
                continue
            align = detect_align([s["left"] for s in matched], b["bbox"][0], b["bbox"][2])
            fs = aggregate_font(matched, align=align)
            if fs:
                result[b["span_id"]] = fs
        doc.close()
        return result
    except Exception as e:
        logger.warning(f"extract_page_fonts failed for {pdf_path} p{page_no}: {e}")
        return {}
