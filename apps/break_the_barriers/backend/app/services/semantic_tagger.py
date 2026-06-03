"""Assign a semantic role to each PyMuPDF text block by overlapping it with the
best-matching docling item (which carries the semantic label)."""
from __future__ import annotations
from typing import List, Dict

from backend.app.services.typography_extractor import iou

_LABEL_ROLE = {
    "section_header": "heading", "title": "heading",
    "list_item": "list", "table": "table", "caption": "caption",
}


def label_to_role(label) -> str:
    return _LABEL_ROLE.get(str(label or "").lower(), "body")


def tag_blocks(blocks: List[Dict], docling_items: List[Dict],
               iou_threshold: float = 0.1) -> List[Dict]:
    """For each block, pick the docling item with highest IoU >= threshold and use
    its role; otherwise 'body'. docling_items: [{"label", "bbox":[l,t,w,h]}].
    Mutates blocks in place (adds 'role') and returns them."""
    for b in blocks:
        best_role = "body"
        best_iou = iou_threshold
        for it in docling_items:
            bb = it.get("bbox")
            if not bb:
                continue
            ov = iou(b["bbox"], bb)
            if ov >= best_iou:
                best_iou = ov
                best_role = label_to_role(it.get("label"))
        b["role"] = best_role
    return blocks
