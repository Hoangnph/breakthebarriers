"""Render a text-page PageModel as real positioned HTML/CSS — translated text in
matched fonts, figures as cropped images, NO full-page raster, NO opaque boxes.

SP-A uses absolute positioning (faithful to source coordinates) with a
client-side shrink-to-fit refinement. Flow mode is reserved for SP-B export."""
from __future__ import annotations
import html as html_lib
import re

from backend.app.services.page_model import PageModel
from backend.app.services.text_fitter import fit_font_size
from backend.app.services.background_policy import resolve_background_policy, effective_policy
from backend.app.services.toc_parser import parse_toc_entry, is_toc_page

# Vietnamese-capable web fonts, one per family class.
_FONT_STACK = {
    "sans":  "'Be Vietnam Pro', system-ui, sans-serif",
    "serif": "'Source Serif 4', Georgia, serif",
    "mono":  "'JetBrains Mono', ui-monospace, monospace",
}
_GOOGLE_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Be+Vietnam+Pro:ital,wght@0,400;0,700;1,400&'
    'family=Source+Serif+4:ital,wght@0,400;0,700;1,400&'
    'family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">'
)

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body { background: #525659; }
.tl-scroll { position: absolute; inset: 0; overflow: auto; }
.tl-fit { min-width: 100%; min-height: 100%; display: flex;
          align-items: center; justify-content: center; padding: 12px; }
.tl-canvas { position: relative; flex: 0 0 auto; }
.tl-page { position: absolute; top: 0; left: 0; transform-origin: top left;
           box-shadow: 0 2px 14px rgba(0,0,0,.45); overflow: hidden;
           visibility: hidden; }
.tl-fig { position: absolute; display: block; }
.tl-bg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.tl-text { position: absolute; line-height: 1.2; overflow: hidden;
           word-break: break-word; }
.tl-toc { display: flex; align-items: flex-end; white-space: nowrap; }
.tl-toc-title { flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; }
.tl-toc-leader { flex: 1 1 8px; min-width: 8px; margin: 0 4px 3px;
                 border-bottom: 1px dotted currentColor; }
.tl-toc-num { flex: 0 0 auto; }
"""


def _opaque_fill(fill: str, min_alpha: float = 0.9) -> str:
    """Raise an rgba fill's alpha to at least min_alpha so the mask hides the
    baked-in original text under an overlaid translation. Solid/hex colors (already
    opaque) pass through unchanged."""
    m = re.match(
        r"\s*rgba\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)\s*$",
        fill)
    if not m:
        return fill
    r, g, b, a = m.groups()
    return f"rgba({r},{g},{b},{max(float(a), min_alpha)})"


def _mask_css(box) -> str:
    """CSS background that masks the original text region behind an overlaid block.
    Empty string when there is no box fill."""
    if not box or not box.get("fill"):
        return ""
    fill = _opaque_fill(box["fill"])
    pad = "padding:0 2px;" if box.get("mode") == "scrim" else ""
    return f"background:{fill};{pad}"


def _pct(v: float, total: float) -> float:
    return v / total * 100.0 if total else 0.0


def _x_overlap_frac(a: list, b: list) -> float:
    """Fraction of the narrower box's width covered by the horizontal overlap
    of two bboxes [l, t, w, h]. 0.0 means no horizontal overlap."""
    al, aw = a[0], a[2]
    bl, bw = b[0], b[2]
    ov = min(al + aw, bl + bw) - max(al, bl)
    if ov <= 0:
        return 0.0
    return ov / max(1.0, min(aw, bw))


def compute_slot_heights(blocks: list, figures: list, page_h: float,
                         *, overlap_frac: float = 0.25) -> dict:
    """For each block, the vertical slot from its top down to the nearest
    obstacle below it (a block or figure whose x-range overlaps by at least
    `overlap_frac`), floored at the block's own height. Points in, points out."""
    obstacles = [fig.bbox for fig in figures] + [b.bbox for b in blocks]
    slots: dict = {}
    for blk in blocks:
        l, t, w, h = blk.bbox
        nearest = float(page_h)
        for ob in obstacles:
            if ob is blk.bbox:
                continue
            ot = ob[1]
            if ot <= t:
                continue
            if _x_overlap_frac(blk.bbox, ob) < overlap_frac:
                continue
            nearest = min(nearest, ot)
        slots[blk.span_id] = max(h, nearest - t)
    return slots


def render_text_layer(model: PageModel, translations: dict, image_url_base: str) -> str:
    pw = model.page_w or 1.0
    ph = model.page_h or 1.0
    bg = (model.background or {}).get("color") or "#ffffff"

    policy = effective_policy(model.page_class, model.cover,
                              (model.background or {}).get("policy_override"))
    draw_raster = policy != "base-color"
    # On a base-color page the original raster is dropped, so render on a clean
    # WHITE page — not the dark color sampled from the discarded photo.
    if policy == "base-color":
        bg = "#ffffff"

    parts = []
    bgd = model.background or {}
    image_name = bgd.get("image")
    if policy == "clean-photo" and bgd.get("clean_image"):
        image_name = bgd.get("clean_image")
    if image_name and draw_raster:
        bg_src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="tl-bg" src="{bg_src}" alt="page"/>')
    # Figures first (z-order below text).
    for fig in model.figures:
        l, t, w, h = fig.bbox
        fig_name = fig.clean_img or fig.img
        src = html_lib.escape(f"{image_url_base}/{fig_name}", quote=True)
        parts.append(
            f'<img class="tl-fig" src="{src}" alt="figure" '
            f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
            f'width:{_pct(w, pw):.3f}%;height:{_pct(h, ph):.3f}%;"/>'
        )

    slots = compute_slot_heights(model.blocks, model.figures, ph)

    toc_page = is_toc_page([(translations or {}).get(b.span_id, "") for b in model.blocks])

    for blk in model.blocks:
        text = (translations or {}).get(blk.span_id)
        if not text:
            continue
        l, t, w, h = blk.bbox
        f = blk.font
        family = _FONT_STACK.get(f.family_class if f else "sans", _FONT_STACK["sans"])
        color = (f.color if f else "#1a1a1a")
        weight = (f.weight if f else (700 if blk.role == "heading" else 400))
        italic = "italic" if (f and f.italic) else "normal"
        align = (f.align if f else "left")
        slot_h = slots.get(blk.span_id, h)
        # A single-line block (a title/label whose original box is ~1 line) fits
        # to its bbox so a longer translation shrinks instead of wrapping off its
        # designed region (e.g. a title off its banner). Multi-line body keeps the
        # L3 slot growth to avoid tiny text. role is often mislabelled, so also
        # detect single-line geometry from the bbox height vs font size.
        f_size = f.size if f and f.size else 0
        is_single_line = blk.role == "heading" or (f_size and h <= f_size * 1.8)
        fit_h = h if is_single_line else slot_h
        max_h = h if is_single_line else slot_h
        base = (f.size if f and f.size else max(8.0, h * 0.8))
        size = fit_font_size(text, w, fit_h, max_size=base, min_size=6.0,
                             height_growth=1.0)
        box = blk.box or None
        box_css = ""
        if box and box.get("fill") and policy == "keep-raster":
            if box.get("mode") == "scrim":
                box_css = f"background:{box['fill']};padding:0 2px;"
            else:
                box_css = f"background:{box['fill']};"
        entry = parse_toc_entry(text) if toc_page else None
        if entry:
            _title, _num = entry
            inner = (f'<span class="tl-toc-title">{html_lib.escape(_title)}</span>'
                     f'<span class="tl-toc-leader"></span>'
                     f'<span class="tl-toc-num">{html_lib.escape(_num)}</span>')
            cls = "tl-text tl-toc"
        else:
            inner = html_lib.escape(text)
            cls = "tl-text"
        parts.append(
            f'<div class="{cls}" data-fit="1" '
            f'data-span="{html_lib.escape(blk.span_id, quote=True)}" '
            f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
            f'width:{_pct(w, pw):.3f}%;'
            f'min-height:{_pct(h, ph):.3f}%;max-height:{_pct(max_h, ph):.3f}%;'
            f'font-family:{family};font-size:{size:.1f}px;font-weight:{weight};'
            f'font-style:{italic};color:{color};text-align:{align};{box_css}">'
            f'{inner}</div>'
        )

    script = (
        "<script>(function(){"
        f"var PW={pw:.2f},PH={ph:.2f},pad=24,userZoom=1;"
        "function fitText(){var ds=document.querySelectorAll('.tl-text[data-fit]');"
        "ds.forEach(function(d){var g=0;"
        "while(d.scrollHeight>d.clientHeight+1&&g<40){"
        "var fs=parseFloat(getComputedStyle(d).fontSize);if(fs<=6)break;"
        "d.style.fontSize=(fs-0.5)+'px';g++;}/*btb-fit*/});}"
        "function apply(){var p=document.querySelector('.tl-page'),"
        "c=document.querySelector('.tl-canvas');if(!p||!c)return;"
        "var fit=Math.min((window.innerWidth-pad)/PW,(window.innerHeight-pad)/PH);"
        "var s=fit*userZoom;p.style.transform='scale('+s+')';"
        "c.style.width=(PW*s)+'px';c.style.height=(PH*s)+'px';"
        "p.style.visibility='visible';}"
        "function run(){fitText();apply();}"
        "window.addEventListener('resize',apply);"
        "window.addEventListener('message',function(e){var d=e.data||{};"
        "if(d.type==='btb-zoom'&&typeof d.zoom==='number'){"
        "userZoom=Math.max(0.25,Math.min(5,d.zoom));apply();}});"
        "document.addEventListener('click',function(e){"
        "var el=e.target.closest&&e.target.closest('.tl-text');if(!el)return;"
        "window.parent.postMessage({type:'btb-edit',"
        "span_id:el.getAttribute('data-span'),text:el.textContent},'*');});/*btb-edit*/"
        "if(document.readyState!=='loading')run();"
        "else window.addEventListener('DOMContentLoaded',run);"
        "window.addEventListener('load',run);})();</script>"
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"{_GOOGLE_FONTS}<style>{_CSS}</style></head><body>"
        f'<div class="tl-scroll"><div class="tl-fit"><div class="tl-canvas">'
        f'<div class="tl-page" style="width:{pw:.2f}px;height:{ph:.2f}px;'
        f'background:{html_lib.escape(bg, quote=True)};">'
        f'{"".join(parts)}</div></div></div></div>{script}</body></html>'
    )
