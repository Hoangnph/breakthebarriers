"""Render PDF → HTML element THẬT, RELATIVE (responsive) giữ cấu trúc gốc.
Trang = container co giãn (aspect-ratio + container-type:inline-size); block định vị
theo %; cỡ chữ theo cqw (tương ứng bề rộng trang) → không còn absolute px cứng.
Mỗi đoạn = block, mỗi dòng giữ style span thật (font/màu/đậm-nghiêng); ảnh = <img> %."""
import html as html_lib
from typing import Dict, Any, List

_FLOW_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#8a8d91}
.pf{position:relative;width:96%;max-width:880px;margin:18px auto;background:#fff;
    container-type:inline-size;box-shadow:0 2px 10px rgba(0,0,0,.35);overflow:hidden}
.pf .bk{position:absolute}
.pf .sec{position:absolute}
.pf .col{position:absolute}
.pf .ln{position:absolute;white-space:nowrap;line-height:1.04}
.pf .ln span{white-space:pre}
.pf img{position:absolute;display:block}
.pf .vec{position:absolute;inset:0;width:100%;height:100%}
"""


def _vector_svg(drawings: List[Dict[str, Any]], w: float, h: float) -> str:
    """Đồ hoạ vector → 1 lớp <svg> (viewBox theo điểm PDF) co giãn cùng trang."""
    if not drawings:
        return ""
    paths = []
    for d in drawings:
        attrs = [f'd="{d["d"]}"', f'fill="{d["fill"] or "none"}"']
        if d.get("stroke"):
            attrs.append(f'stroke="{d["stroke"]}"')
            attrs.append(f'stroke-width="{max(d.get("width") or 0, 0.3):.2f}"')
        paths.append(f'<path {" ".join(attrs)}/>')
    return (f'<svg class="vec" viewBox="0 0 {w:.2f} {h:.2f}" '
            f'preserveAspectRatio="none">{"".join(paths)}</svg>')


def _esc(s: str) -> str:
    return html_lib.escape(s)


# ── Renderer theo cây layout (section/band/cột lồng nhau, ĐỊNH VỊ vị trí thật) ──

def _render_lines(blk: Dict[str, Any], page_w: float) -> str:
    """Mỗi LINE định vị theo bbox thật trong block → line cùng baseline (vd
    footer trái/giữa/phải) GIỮ CÙNG HÀNG, không xếp chồng thành nhiều dòng."""
    bx, by, bw, bh = blk["bbox"]
    bw = max(bw, 1.0)
    bh = max(bh, 1.0)
    out = []
    for line in blk["lines"]:
        lx, ly, lw, _lh = line["bbox"]
        out.append(
            f'<div class="ln" style="left:{(lx - bx) / bw * 100:.3f}%;'
            f'top:{(ly - by) / bh * 100:.3f}%;width:{lw / bw * 100:.3f}%">')
        for s in line["spans"]:
            style = (f'font-size:{s["size"] / page_w * 100:.3f}cqw;'
                     f'font-family:{s["font"]};color:{s["color"]};')
            if s.get("bold"):
                style += "font-weight:bold;"
            if s.get("italic"):
                style += "font-style:italic;"
            out.append(f'<span style="{style}">{_esc(s["text"])}</span>')
        out.append('</div>')
    return "".join(out)


def _render_block_at(blk: Dict[str, Any], px: float, py: float, pw: float,
                     ph: float, page_w: float) -> str:
    """Block định vị theo vị trí THẬT (% trong parent), có height để line con định
    vị đúng → giữ đúng hàng/cột gốc, 1 dòng vẫn là 1 dòng."""
    bx, by, bw, bh = blk["bbox"]
    left = (bx - px) / max(pw, 1.0) * 100
    top = (by - py) / max(ph, 1.0) * 100
    width = bw / max(pw, 1.0) * 100
    height = bh / max(ph, 1.0) * 100
    return (f'<div class="bk" style="left:{left:.3f}%;top:{top:.3f}%;'
            f'width:{width:.3f}%;height:{height:.3f}%">{_render_lines(blk, page_w)}</div>')


def render_analyzed_page(t: Dict[str, Any], asset_base: str = "") -> str:
    """section định vị relative TRANG (role header/footer giữ 1 hàng); band→cột
    LỒNG NHAU (cột relative band); block định vị vị trí thật trong section/cột."""
    w = t.get("page_w") or 900.0
    h = t.get("page_h") or 1260.0
    if w <= 0:
        w = 900.0
    parts: List[str] = [f'<div class="pf" style="aspect-ratio:{w:.2f}/{h:.2f}">']

    vec = _vector_svg(t.get("drawings", []), w, h)
    if vec:
        parts.append(vec)
    for im in t.get("images", []):
        x, y, iw, ih = im["bbox"]
        name = im.get("name", "")
        if not name:
            continue
        src = f"{asset_base}/{name}" if asset_base else name
        parts.append(
            f'<img src="{_esc(src)}" style="left:{x / w * 100:.3f}%;top:{y / h * 100:.3f}%;'
            f'width:{iw / w * 100:.3f}%;height:{ih / h * 100:.3f}%">')

    for sec in t.get("sections", []):
        sx, sy, sw, sh = sec["bbox"]
        sw = max(sw, 1.0)
        sh = max(sh, 1.0)
        role = sec.get("role", "")
        cls = "sec" + (f" {role}" if role else "")
        parts.append(
            f'<div class="{cls}" style="left:{sx / w * 100:.3f}%;top:{sy / h * 100:.3f}%;'
            f'width:{sw / w * 100:.3f}%;height:{sh / h * 100:.3f}%">')
        if sec.get("kind") == "band":
            for col in sec["columns"]:
                cx, cy, cw, ch = col["bbox"]
                cw = max(cw, 1.0)
                ch = max(ch, 1.0)
                parts.append(
                    f'<div class="col" style="left:{(cx - sx) / sw * 100:.3f}%;'
                    f'top:{(cy - sy) / sh * 100:.3f}%;width:{cw / sw * 100:.3f}%;'
                    f'height:{ch / sh * 100:.3f}%">')
                for b in col["blocks"]:
                    parts.append(_render_block_at(b, cx, cy, cw, ch, w))
                parts.append('</div>')
        else:
            for b in sec["blocks"]:
                parts.append(_render_block_at(b, sx, sy, sw, sh, w))
        parts.append('</div>')

    parts.append('</div>')
    return "".join(parts)


def render_analyzed_flow(trees: List[Dict[str, Any]], asset_base: str = "") -> str:
    """Nhiều trang (đã phân tích layout) xếp dọc → 1 tài liệu HTML responsive."""
    body = "\n".join(render_analyzed_page(t, asset_base) for t in trees)
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<style>{_FLOW_CSS}</style></head><body>{body}</body></html>")
