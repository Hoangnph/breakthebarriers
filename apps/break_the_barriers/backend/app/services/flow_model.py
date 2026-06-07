"""Build a single flowing-document model (ordered FlowElements) from a list of
per-page PageModels. Content pages flow their text blocks (+ cut figures) as HTML.
A page is kept as a single full-page image_block ONLY (text NOT re-flowed) when it
is image-dominant: a cover, or a clean-photo/keep-raster page with very few text
blocks (<= _DESIGN_MAX_TEXT_BLOCKS). Text-heavy keep-raster pages (often just an
uncertain `preserve` classification) still flow as HTML so their content stays
readable/translatable. Pure: structure only — text is filled from translations."""
from __future__ import annotations
import re
from dataclasses import dataclass
from collections import Counter, defaultdict
from typing import Iterable, List, Optional, Tuple

from backend.app.services.page_model import PageModel
from backend.app.services.background_policy import effective_policy

# A design page (cover/diagram) shows as a full-page image only. For non-cover
# pages we additionally require few text blocks, so that content pages wrongly
# marked `preserve` (→ keep-raster) still flow as readable HTML.
_DESIGN_MAX_TEXT_BLOCKS = 4

# A banner-with-title overlay is only safe when the figure background has been
# text-cleaned (else we'd double the baked-in text) and it holds at most a title
# or two (a figure overlapping many text blocks is a content region, not a banner).
# A real banner also spans most of the page width and carries a large title — this
# excludes example images, icons and captions that merely overlap a small label.
_BANNER_MAX_BLOCKS = 2
_BANNER_MIN_WIDTH_FRAC = 0.8
_BANNER_MIN_TITLE_SIZE = 16.0


def _is_banner_title(block, fig, page_w: float) -> bool:
    """A figure is a banner (with an overlaid section title) only when it is wide
    (spans most of the page) and the overlaid block is a large title. The
    background is the verified clean image when available (title sits directly on
    it), otherwise the original image with a covering band behind the title."""
    if (fig.bbox[2] or 0) < _BANNER_MIN_WIDTH_FRAC * page_w:
        return False                       # narrow figure → example image/icon, not banner
    size = block.font.size if block.font and block.font.size else 0
    return size >= _BANNER_MIN_TITLE_SIZE


@dataclass
class FlowElement:
    kind: str                      # heading|paragraph|caption|list|figure|image_block
    span_id: Optional[str] = None
    level: int = 0                 # heading: 1..3
    src: Optional[str] = None      # figure/image_block filename
    # When set, this text element is a title overlaid on a banner image (the page
    # design had the text on top of the figure). Keys: src (figure file), left/top/
    # width (% of figure box), color, weight, align, size_cqw (font-size in cqw).
    overlay: Optional[dict] = None


def flow_span_id(page_num: int, span_id: Optional[str]) -> Optional[str]:
    """Globally-unique key for a page-local span_id. Used for both flow anchor ids
    and the render-time translation dict so they stay in sync across pages."""
    if span_id is None:
        return None
    return f"p{page_num}-{span_id}"


_RUNNING_MAX_LEN = 80          # running headers/footers are short lines


def _norm_hf(text: str) -> str:
    """Normalize a line for running-header/footer matching: lowercase, drop digits
    (page numbers vary), collapse whitespace. Empty if nothing meaningful remains."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "", (text or "").lower())).strip()


def running_header_spans(entries: Iterable[Tuple[int, str, str]]) -> set:
    """Identify running headers/footers from per-page text and return the set of
    flow span ids (``p{page}-{span}``) to drop from the flow.

    ``entries`` are ``(page_num, span_id, text)`` triples (use the ORIGINAL text —
    it is fully populated for every page, unlike sparse translations). A short line
    whose normalized form recurs on >= 25% of pages (min 3) is treated as a running
    header/footer. No-op for documents with fewer than 4 pages."""
    pages_with: dict = defaultdict(set)
    norm_spans: dict = defaultdict(list)
    all_pages: set = set()
    for page_num, span_id, text in entries:
        all_pages.add(page_num)
        t = (text or "").strip()
        if not t or len(t) > _RUNNING_MAX_LEN:
            continue
        n = _norm_hf(t)
        if not n:
            continue
        pages_with[n].add(page_num)
        norm_spans[n].append(flow_span_id(page_num, span_id))
    if len(all_pages) < 4:
        return set()
    threshold = max(3, round(len(all_pages) * 0.25))
    out: set = set()
    for n, ps in pages_with.items():
        if len(ps) >= threshold:
            out.update(norm_spans[n])
    return out


def _body_size(pages: List[PageModel]) -> float:
    sizes = [b.font.size for p in pages for b in p.blocks
             if b.role == "body" and b.font and b.font.size]
    if not sizes:
        return 11.0
    return Counter(sizes).most_common(1)[0][0]


def _is_heading(b, body_size: float) -> bool:
    fs = b.font.size if b.font and b.font.size else 0
    return b.role == "heading" or (fs and fs >= body_size * 1.3)


def _center_inside(b_bbox, f_bbox) -> bool:
    """True if the block's center lies inside the figure rect (bbox = x0,y0,w,h)
    and the figure is strictly larger — i.e. the block sits on top of the figure."""
    bx, by, bw, bh = b_bbox
    fx, fy, fw, fh = f_bbox
    if fw <= 0 or fh <= 0 or fw * fh <= bw * bh:
        return False
    cx, cy = bx + bw / 2, by + bh / 2
    return fx <= cx <= fx + fw and fy <= cy <= fy + fh


def _make_overlay(block, fig) -> dict:
    """Position/style for a title block overlaid on a banner figure. Percentages are
    relative to the figure box; font-size is in cqw (relative to figure width). When
    the figure has no verified clean image, `band` is True so the renderer draws a
    covering band behind the title (hiding the baked-in text) over the original."""
    bx, by, bw, bh = block.bbox
    fx, fy, fw, fh = fig.bbox
    f = block.font
    align = f.align if (f and f.align in ("left", "center", "right", "justify")) else "left"
    color = f.color if (f and f.color and re.match(r"^#[0-9a-fA-F]{3,8}$", f.color)) else "#ffffff"
    weight = int(f.weight) if (f and f.weight) else 700
    size = (f.size if f and f.size else 16)
    return {
        "src": fig.clean_img or fig.img,
        "band": fig.clean_img is None,
        "left": round((bx - fx) / fw * 100, 2),
        "top": round((by - fy) / fh * 100, 2),
        "width": round(bw / fw * 100, 2),
        "height": round(bh / fh * 100, 2),
        "color": color,
        "weight": weight,
        "align": align,
        "size_cqw": round(size / fw * 100, 2),
    }


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
        # Bond each figure to a single title block sitting on top of it (banner with
        # overlaid title). The figure is then rendered via that block's overlay, not
        # as a standalone figure — so title and image stay together as in the design.
        overlay_for: dict = {}      # id(block) -> overlay dict
        consumed_figs: set = set()  # id(fig)
        for f in p.figures:
            contained = [b for b in p.blocks
                         if _center_inside(b.bbox, f.bbox)]
            # Overlay only on a text-cleaned banner holding a title or two — never
            # on a raw figure (would double its baked text) nor on a figure that
            # overlaps many text blocks (that is a content region, not a banner).
            if not contained or len(contained) > _BANNER_MAX_BLOCKS:
                continue
            headings = [b for b in contained if _is_heading(b, body_size)]
            primary = (headings or sorted(
                contained,
                key=lambda b: -(b.font.size if b.font and b.font.size else 0)))[0]
            if not _is_banner_title(primary, f, p.page_w):
                continue                    # not a wide titled banner → leave as figure
            overlay_for[id(primary)] = _make_overlay(primary, f)
            consumed_figs.add(id(f))

        items = [("blk", b, b.bbox[1]) for b in p.blocks] + \
                [("fig", f, f.bbox[1]) for f in p.figures if id(f) not in consumed_figs]
        items.sort(key=lambda it: it[2])
        for tag, obj, _top in items:
            if tag == "fig":
                # Standalone (non-banner) figures keep their ORIGINAL image — never
                # the AI-cleaned one, which can lose content (faces, labels).
                flow.append(FlowElement(kind="figure", src=obj.img))
                continue
            # span_id is only unique within a page; namespace by page_num so anchors
            # and translation keys never collide across the flattened document.
            sid = flow_span_id(p.page_num, obj.span_id)
            ov = overlay_for.get(id(obj))
            if _is_heading(obj, body_size):
                flow.append(FlowElement(kind="heading", span_id=sid, level=level(obj), overlay=ov))
            elif obj.role == "caption":
                flow.append(FlowElement(kind="caption", span_id=sid, overlay=ov))
            elif obj.role == "list":
                flow.append(FlowElement(kind="list", span_id=sid, overlay=ov))
            else:
                flow.append(FlowElement(kind="paragraph", span_id=sid, overlay=ov))
    return flow
