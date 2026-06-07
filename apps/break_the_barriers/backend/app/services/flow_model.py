"""Build a single flowing-document model (ordered FlowElements) from a list of
per-page PageModels. Content pages flow their text blocks (+ cut figures) as HTML.
A page is kept as a single full-page image_block ONLY (text NOT re-flowed) when it
is image-dominant: a cover, or a clean-photo/keep-raster page with very few text
blocks (<= _DESIGN_MAX_TEXT_BLOCKS). Text-heavy keep-raster pages (often just an
uncertain `preserve` classification) still flow as HTML so their content stays
readable/translatable. Pure: structure only — text is filled from translations."""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from typing import List, Optional

from backend.app.services.page_model import PageModel
from backend.app.services.background_policy import effective_policy

# A design page (cover/diagram) shows as a full-page image only. For non-cover
# pages we additionally require few text blocks, so that content pages wrongly
# marked `preserve` (→ keep-raster) still flow as readable HTML.
_DESIGN_MAX_TEXT_BLOCKS = 4


@dataclass
class FlowElement:
    kind: str                      # heading|paragraph|caption|list|figure|image_block
    span_id: Optional[str] = None
    level: int = 0                 # heading: 1..3
    src: Optional[str] = None      # figure/image_block filename


def flow_span_id(page_num: int, span_id: Optional[str]) -> Optional[str]:
    """Globally-unique key for a page-local span_id. Used for both flow anchor ids
    and the render-time translation dict so they stay in sync across pages."""
    if span_id is None:
        return None
    return f"p{page_num}-{span_id}"


def _body_size(pages: List[PageModel]) -> float:
    sizes = [b.font.size for p in pages for b in p.blocks
             if b.role == "body" and b.font and b.font.size]
    if not sizes:
        return 11.0
    return Counter(sizes).most_common(1)[0][0]


def _is_heading(b, body_size: float) -> bool:
    fs = b.font.size if b.font and b.font.size else 0
    return b.role == "heading" or (fs and fs >= body_size * 1.3)


def build_document_flow(pages: List[PageModel]) -> List[FlowElement]:
    body_size = _body_size(pages)
    heading_sizes = sorted(
        {(b.font.size if b.font and b.font.size else 0)
         for p in pages for b in p.blocks if _is_heading(b, body_size)},
        reverse=True)

    def level(b) -> int:
        fs = b.font.size if b.font and b.font.size else 0
        try:
            return min(heading_sizes.index(fs) + 1, 3)
        except ValueError:
            return 3

    flow: List[FlowElement] = []
    for p in pages:
        policy = effective_policy(p.page_class, p.cover,
                                  (p.background or {}).get("policy_override"))
        is_cover = p.cover in ("front", "back")
        image_only = policy in ("clean-photo", "keep-raster") and (
            is_cover or len(p.blocks) <= _DESIGN_MAX_TEXT_BLOCKS)
        if image_only:
            # Image-dominant page (cover / sparse design): keep the full-page image
            # only and do NOT re-flow its text. Prefer the original raster
            # (self-complete, e.g. cover with its title) over the cleaned one.
            bgd = p.background or {}
            src = bgd.get("image") or bgd.get("clean_image")
            if src:
                flow.append(FlowElement(kind="image_block", src=src))
                continue
        items = [("blk", b, b.bbox[1]) for b in p.blocks] + \
                [("fig", f, f.bbox[1]) for f in p.figures]
        items.sort(key=lambda it: it[2])
        for tag, obj, _top in items:
            if tag == "fig":
                flow.append(FlowElement(kind="figure", src=(obj.clean_img or obj.img)))
                continue
            # span_id is only unique within a page; namespace by page_num so anchors
            # and translation keys never collide across the flattened document.
            sid = flow_span_id(p.page_num, obj.span_id)
            if _is_heading(obj, body_size):
                flow.append(FlowElement(kind="heading", span_id=sid, level=level(obj)))
            elif obj.role == "caption":
                flow.append(FlowElement(kind="caption", span_id=sid))
            elif obj.role == "list":
                flow.append(FlowElement(kind="list", span_id=sid))
            else:
                flow.append(FlowElement(kind="paragraph", span_id=sid))
    return flow
