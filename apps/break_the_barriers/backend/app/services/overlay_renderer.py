import html as html_lib
import math
import re

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")

_OVERLAY_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
.ov-page { position: relative; width: 100%; max-width: 900px; margin: 0 auto; }
.ov-bg { display: block; width: 100%; height: auto; }
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
    css = _OVERLAY_CSS if parts else "* { box-sizing: border-box; margin: 0; padding: 0; } .ov-page { position: relative; width: 100%; max-width: 900px; margin: 0 auto; } .ov-bg { display: block; width: 100%; height: auto; }"
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<style>{css}</style></head><body>"
        f'<div class="ov-page">{img_tag}{"".join(parts)}</div>'
        "</body></html>"
    )
