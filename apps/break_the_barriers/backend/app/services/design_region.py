"""Detect composite design regions (e.g. chat: avatar icons interleaved with text)
that must render as one faithful raster crop, not decomposed into scattered figures +
reflowed text — and infer per-figure horizontal alignment. Pure geometry; the actual
cropping/IO happens in the caller (extractor / backfill). bbox = [x0, y0, w, h] pts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Set

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


@dataclass
class Region:
    bbox: List[float]                       # [x0, y0, w, h] union (page points)
    figure_idx: Set[int] = field(default_factory=set)
    block_ids: Set[str] = field(default_factory=set)


def _is_icon(bbox, page_w: float, page_h: float) -> bool:
    return bool(page_w and page_h
                and bbox[2] < _ICON_MAX_FRAC * page_w
                and bbox[3] < _ICON_MAX_FRAC * page_h)


def detect_design_regions(fig_bboxes, blocks, page_w: float, page_h: float,
                          min_icons: int = 2, min_span_frac: float = 0.2) -> List["Region"]:
    """Find composite design regions: pages whose layout is built from >= min_icons
    icon-figures spanning a tall vertical band with body text interleaved (chat-like).
    Such a band must be one faithful crop. Returns at most one region per page.

    `fig_bboxes`: List[[x0,y0,w,h]]. `blocks`: List[(span_id, [x0,y0,w,h])]."""
    if not page_h:
        return []
    icon_idx = [i for i, b in enumerate(fig_bboxes) if _is_icon(b, page_w, page_h)]
    if len(icon_idx) < min_icons:
        return []
    icon_bb = [fig_bboxes[i] for i in icon_idx]
    top = min(b[1] for b in icon_bb)
    bot = max(b[1] + b[3] for b in icon_bb)
    if (bot - top) < min_span_frac * page_h:
        return []
    member_figs: Set[int] = {i for i, b in enumerate(fig_bboxes)
                             if top <= (b[1] + b[3] / 2) <= bot}
    member_figs |= set(icon_idx)
    band_blocks = [(sid, bb) for sid, bb in blocks
                   if top <= (bb[1] + bb[3] / 2) <= bot]
    if not band_blocks:
        return []
    allbb = [fig_bboxes[i] for i in member_figs] + [bb for _sid, bb in band_blocks]
    x0 = min(b[0] for b in allbb)
    y0 = min(b[1] for b in allbb)
    x1 = max(b[0] + b[2] for b in allbb)
    y1 = max(b[1] + b[3] for b in allbb)
    pad = 6.0
    return [Region(
        bbox=[max(0.0, x0 - pad), max(0.0, y0 - pad),
              (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad],
        figure_idx=set(member_figs),
        block_ids={sid for sid, _bb in band_blocks},
    )]
