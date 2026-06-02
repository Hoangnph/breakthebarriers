import html as html_lib
import math
import re

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")

_OVERLAY_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
    background: #525659;
    overflow: auto;
    display: flex;
    align-items: safe center;
    justify-content: safe center;
}
.ov-canvas { position: relative; flex: 0 0 auto; }
.ov-page {
    position: absolute;
    top: 0; left: 0;
    transform-origin: top left;
    background: #fff;
    box-shadow: 0 2px 14px rgba(0,0,0,.45);
    visibility: hidden;
}
.ov-bg { display: block; width: 100%; height: 100%; }
.ov-text {
    position: absolute;
    line-height: 1.15;
    overflow: visible;
    word-break: break-word;
    padding: 0 1px;
}
"""


def _text_color(bg_hex: str) -> str:
    """Black on light backgrounds, white on dark — based on luminance."""
    try:
        h = bg_hex.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"
    except Exception:
        return "#000000"


def _fit_font_size(text: str, box_w_pt: float, box_h_pt: float) -> float:
    """Largest font (px, in page-point space) so text wraps within the box.
    Allows vertical growth up to 1.6x the box height before shrinking further."""
    n = max(len(text or ""), 1)
    best = 6.0
    fs = 6.0
    while fs <= 40.0:
        chars_per_line = max(1.0, box_w_pt / (0.5 * fs))
        lines = math.ceil(n / chars_per_line)
        if lines * fs * 1.25 <= max(box_h_pt, fs) * 1.6:
            best = fs
        fs += 0.5
    return best


def render_overlay_html(layout: dict, translations: dict, image_url_base: str) -> str:
    """Build a self-contained HTML page: raster background + absolutely-positioned
    translated-text divs (in %). Empty translations → raster only (faithful original)."""
    pw = layout.get("page_w") or 1.0
    ph = layout.get("page_h") or 1.0
    image = layout.get("image")
    blocks = layout.get("blocks") or []

    parts = []
    for blk in blocks:
        sid = blk.get("span_id")
        text = (translations or {}).get(sid)
        if not text:
            continue
        bbox = blk.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        l, t, w, h = bbox
        left = l / pw * 100.0
        top = t / ph * 100.0
        width = w / pw * 100.0
        bg = blk.get("bg", "#ffffff")
        if not isinstance(bg, str) or not _HEX_RE.match(bg):
            bg = "#ffffff"
        fs = _fit_font_size(text, w, h)
        parts.append(
            f'<div class="ov-text" style="left:{left:.3f}%;top:{top:.3f}%;'
            f'width:{width:.3f}%;background:{bg};color:{_text_color(bg)};'
            f'font-size:{fs:.1f}px;">{html_lib.escape(text)}</div>'
        )

    img_src = html_lib.escape(f"{image_url_base}/{image}", quote=True) if image else ""
    img_tag = f'<img class="ov-bg" src="{img_src}" alt="page"/>' if image else ""

    # The page keeps its natural point-space size; a uniform transform:scale renders it.
    # scale = fitScale * userZoom — fit fills the viewport; userZoom (driven by the parent
    # via postMessage) zooms in/out. The .ov-canvas reserves the scaled footprint so the
    # body can scroll when zoomed beyond the viewport. img + text + font scale together.
    fit_script = (
        "<script>(function(){"
        f"var PW={pw:.2f},PH={ph:.2f},pad=24,userZoom=1;"
        "function apply(){"
        "var page=document.querySelector('.ov-page'),canvas=document.querySelector('.ov-canvas');"
        "if(!page||!canvas)return;"
        "var fit=Math.min((window.innerWidth-pad)/PW,(window.innerHeight-pad)/PH);"
        "var s=fit*userZoom;"
        "page.style.transform='scale('+s+')';"
        "canvas.style.width=(PW*s)+'px';canvas.style.height=(PH*s)+'px';"
        "page.style.visibility='visible';}"
        "window.addEventListener('resize',apply);"
        "window.addEventListener('message',function(e){var d=e.data||{};"
        "if(d.type!=='btb-zoom')return;"
        "if(typeof d.zoom==='number')userZoom=Math.max(0.25,Math.min(5,d.zoom));"
        "else if(d.action==='in')userZoom=Math.min(5,userZoom+0.25);"
        "else if(d.action==='out')userZoom=Math.max(0.25,userZoom-0.25);"
        "else if(d.action==='reset')userZoom=1;"
        "apply();});"
        "if(document.readyState!=='loading')apply();"
        "else window.addEventListener('DOMContentLoaded',apply);"
        "window.addEventListener('load',apply);"
        "})();</script>"
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<style>{_OVERLAY_CSS}</style></head><body>"
        f'<div class="ov-canvas">'
        f'<div class="ov-page" style="width:{pw:.2f}px;height:{ph:.2f}px">'
        f'{img_tag}{"".join(parts)}</div>'
        f"</div>{fit_script}</body></html>"
    )
