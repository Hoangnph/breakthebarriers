"""Render a document as a faithful continuous flow: a vertical stack of per-page
fragments. Each page shows its original raster (the truth layer — tables, vector
graphics, multi-column design and banners are preserved because they ARE the raster)
with translated text overlaid on masked text regions. Overlay text is sized in cqw
(1cqw = 1% of the page width) so each page scales fluidly with the column width.
Reuses text_layer_renderer's pure helpers so per-page and flow stay consistent."""
from __future__ import annotations
import html as html_lib
from typing import Dict, List

from backend.app.services.page_model import PageModel
from backend.app.services.text_fitter import fit_font_size
from backend.app.services.toc_parser import parse_toc_entry, is_toc_page
from backend.app.services.text_layer_renderer import (
    _FONT_STACK, _GOOGLE_FONTS, _mask_css, _pct, compute_slot_heights,
    resolve_page_raster)

_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #f4f4f5; }
.ff-doc { max-width: 900px; margin: 0 auto; padding: 16px 12px 80px; }
.ff-page { position: relative; container-type: inline-size; width: 100%;
           margin: 0 0 16px; background: #fff; overflow: hidden;
           box-shadow: 0 2px 14px rgba(0,0,0,.25); border-radius: 2px; }
.ff-bg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.ff-fig { position: absolute; display: block; }
.ff-text { position: absolute; line-height: 1.2; overflow: hidden; word-break: break-word; }
.ff-toc { display: flex; align-items: flex-end; white-space: nowrap; }
.ff-toc-title { flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; }
.ff-toc-leader { flex: 1 1 8px; min-width: 8px; margin: 0 4px 3px;
                 border-bottom: 1px dotted currentColor; }
.ff-toc-num { flex: 0 0 auto; }
"""

_SCRIPT = (
    "<script>(function(){"
    "function fit(el){var c=parseFloat(el.dataset.cqw||'0');if(!c)return;var g=0;"
    "el.style.fontSize=c+'cqw';"
    "while(el.scrollHeight>el.clientHeight+1&&c>1&&g<60){c-=0.2;el.style.fontSize=c+'cqw';g++;}}"
    "function run(){document.querySelectorAll('.ff-text').forEach(fit);}"
    "var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(run,150);});"
    "window.addEventListener('message',function(e){var d=e.data||{};"
    "if(d.type==='btb-zoom'&&typeof d.zoom==='number'){"
    "var doc=document.querySelector('.ff-doc');"
    "if(doc)doc.style.maxWidth=Math.max(200,900*d.zoom)+'px';setTimeout(run,0);}});"
    "if(document.readyState!=='loading')run();"
    "else window.addEventListener('DOMContentLoaded',run);"
    "window.addEventListener('load',run);})();</script>"
)


def render_faithful_page(model: PageModel, translations: dict, image_url_base: str) -> str:
    pw = model.page_w or 1.0
    ph = model.page_h or 1.0
    image_name, mask_original, _white = resolve_page_raster(model)
    parts = [f'<section class="ff-page" id="pg-{int(model.page_num)}" '
             f'style="aspect-ratio:{pw:.2f}/{ph:.2f}">']
    if image_name:
        src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="ff-bg" src="{src}" '
                     f'alt="Trang {int(model.page_num)}" loading="lazy"/>')
    for fig in model.figures:
        l, t, w, h = fig.bbox
        fsrc = html_lib.escape(f"{image_url_base}/{fig.clean_img or fig.img}", quote=True)
        parts.append(f'<img class="ff-fig" src="{fsrc}" alt="figure" '
                     f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
                     f'width:{_pct(w, pw):.3f}%;height:{_pct(h, ph):.3f}%;"/>')
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
        f_size = f.size if f and f.size else 0
        is_single_line = blk.role == "heading" or (f_size and h <= f_size * 1.8)
        fit_h = h if is_single_line else slot_h
        max_h = h if is_single_line else slot_h
        base_sz = (f.size if f and f.size else max(8.0, h * 0.8))
        size_px = fit_font_size(text, w, fit_h, max_size=base_sz, min_size=6.0,
                                height_growth=1.0)
        cqw = size_px / pw * 100.0
        box_css = _mask_css(blk.box) if mask_original else ""
        entry = parse_toc_entry(text) if toc_page else None
        if entry:
            _title, _num = entry
            inner = (f'<span class="ff-toc-title">{html_lib.escape(_title)}</span>'
                     f'<span class="ff-toc-leader"></span>'
                     f'<span class="ff-toc-num">{html_lib.escape(_num)}</span>')
            cls = "ff-text ff-toc"
        else:
            inner = html_lib.escape(text)
            cls = "ff-text"
        parts.append(
            f'<div class="{cls}" data-cqw="{cqw:.3f}" '
            f'data-span="{html_lib.escape(blk.span_id, quote=True)}" '
            f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
            f'width:{_pct(w, pw):.3f}%;'
            f'min-height:{_pct(h, ph):.3f}%;max-height:{_pct(max_h, ph):.3f}%;'
            f'font-family:{family};font-size:{cqw:.3f}cqw;font-weight:{weight};'
            f'font-style:{italic};color:{color};text-align:{align};{box_css}">'
            f'{inner}</div>')
    parts.append("</section>")
    return "".join(parts)


def render_faithful_flow(pages: List[PageModel], translations: Dict[int, dict],
                         image_url_base: str) -> str:
    body = "".join(
        render_faithful_page(p, (translations or {}).get(p.page_num, {}), image_url_base)
        for p in sorted(pages, key=lambda m: m.page_num))
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'{_GOOGLE_FONTS}<style>{_CSS}</style></head><body>'
        f'<article class="ff-doc">{body}</article>{_SCRIPT}</body></html>'
    )
