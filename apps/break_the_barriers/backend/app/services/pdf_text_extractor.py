"""Primary page-text source. PyMuPDF extracts ALL text (complete coverage,
including text rendered over images that docling misses). Each PyMuPDF text
block becomes one logical block with bbox + aggregated font."""
from __future__ import annotations
import logging
from typing import List, Dict

from backend.app.services.typography_extractor import aggregate_font, detect_align

logger = logging.getLogger(__name__)


def blocks_from_pymupdf_dict(raw: dict) -> List[Dict]:
    """Group a PyMuPDF `page.get_text('dict')` structure into logical text blocks.

    Returns a list of {"text", "bbox":[l,t,w,h] top-left points, "font": FontSpec}.
    Image blocks (type != 0) and whitespace-only blocks are skipped. No decoration
    filtering here — that happens at translate time."""
    out: List[Dict] = []
    for blk in raw.get("blocks", []):
        if blk.get("type", 0) != 0:
            continue
        span_dicts = []
        line_texts = []
        line_lefts = []
        for line in blk.get("lines", []):
            lb = line.get("bbox")
            if lb:
                line_lefts.append(lb[0])
            parts = []
            for sp in line.get("spans", []):
                parts.append(sp.get("text", ""))
                span_dicts.append({
                    "size": sp.get("size", 0), "flags": sp.get("flags", 0),
                    "color": sp.get("color", 0), "font": sp.get("font", ""),
                })
            line_texts.append("".join(parts))
        text = " ".join(t for t in line_texts).strip()
        if not text or not span_dicts:
            continue
        x0, y0, x1, y1 = blk["bbox"]
        bbox = [x0, y0, x1 - x0, y1 - y0]
        font = aggregate_font(span_dicts, align=detect_align(line_lefts, x0, x1 - x0))
        out.append({"text": text, "bbox": bbox, "font": font})
    return out


def extract_text_blocks(pdf_path: str, page_no: int) -> List[Dict]:
    """Thin PyMuPDF I/O wrapper around blocks_from_pymupdf_dict.
    Returns [] on any failure so the caller can fall back to docling."""
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF not installed; cannot extract text blocks")
        return []
    try:
        doc = fitz.open(pdf_path)
        raw = doc[page_no - 1].get_text("dict")
        doc.close()
        return blocks_from_pymupdf_dict(raw)
    except Exception as e:
        logger.warning(f"extract_text_blocks failed for {pdf_path} p{page_no}: {e}")
        return []
