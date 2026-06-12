"""Render PDF → HTML element THẬT, RELATIVE (responsive) giữ cấu trúc gốc.
Trang = container co giãn (aspect-ratio + container-type:inline-size); block định vị
theo %; cỡ chữ theo cqw (tương ứng bề rộng trang) → không còn absolute px cứng.
Mỗi đoạn = block, mỗi dòng giữ style span thật (font/màu/đậm-nghiêng); ảnh = <img> %."""
import html as html_lib
from typing import Dict, Any, List, Optional

_FLOW_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#8a8d91}
.pf{position:relative;width:96%;max-width:880px;margin:18px auto;background:#fff;
    container-type:inline-size;box-shadow:0 2px 10px rgba(0,0,0,.35);overflow:hidden}
.pf .bk{position:absolute}
.pf .sec{position:absolute}
.pf .col{position:absolute}
.pf .ln{position:absolute;white-space:nowrap;line-height:1.04;transform-origin:0 0}
.pf .ln span{white-space:pre}
.pf .tb{position:absolute;white-space:normal;overflow:visible}
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
        fo = d.get("fill_opacity", 1.0)
        if d.get("fill") and fo < 1.0:                       # nền trong suốt
            attrs.append(f'fill-opacity="{fo:.3f}"')
        if d.get("stroke"):
            attrs.append(f'stroke="{d["stroke"]}"')
            attrs.append(f'stroke-width="{max(d.get("width") or 0, 0.3):.2f}"')
            so = d.get("stroke_opacity", 1.0)
            if so < 1.0:
                attrs.append(f'stroke-opacity="{so:.3f}"')
        paths.append(f'<path {" ".join(attrs)}/>')
    return (f'<svg class="vec" viewBox="0 0 {w:.2f} {h:.2f}" '
            f'preserveAspectRatio="none">{"".join(paths)}</svg>')


def _esc(s: str) -> str:
    return html_lib.escape(s)


def _css_color(hexc: str, alpha: int) -> str:
    """Màu + độ trong suốt: alpha<255 → rgba(r,g,b,a)."""
    if alpha is None or alpha >= 255:
        return hexc
    try:
        r = int(hexc[1:3], 16); g = int(hexc[3:5], 16); b = int(hexc[5:7], 16)
        return f"rgba({r},{g},{b},{max(alpha, 0) / 255:.3f})"
    except Exception:
        return hexc


# ── Renderer theo cây layout (section/band/cột lồng nhau, ĐỊNH VỊ vị trí thật) ──

def _render_lines(blk: Dict[str, Any], page_w: float) -> str:
    """Mỗi LINE định vị theo bbox thật trong block → line cùng baseline (vd
    footer trái/giữa/phải) GIỮ CÙNG HÀNG, không xếp chồng thành nhiều dòng."""
    bx, by, bw, bh = blk["bbox"]
    bw = max(bw, 1.0)
    bh = max(bh, 1.0)
    out = []
    for line in blk["lines"]:
        lx, ly, lw, lh = line["bbox"]
        rot = line.get("rot", 0.0)
        if rot:
            # Chữ xoay/dọc: đặt TÂM div tại tâm AABB rồi xoay quanh tâm (width auto
            # = độ dài chữ thật) → khớp đúng vùng gốc bất kể góc xoay.
            cx = (lx + lw / 2 - bx) / bw * 100
            cy = (ly + lh / 2 - by) / bh * 100
            base = f"translate(-50%,-50%) rotate({rot:.2f}deg)"
            ln_style = (f'left:{cx:.3f}%;top:{cy:.3f}%;white-space:nowrap;'
                        f'transform-origin:50% 50%;transform:{base}')
            rot_attr = f' data-base="{base}"'
        else:
            ln_style = (f'left:{(lx - bx) / bw * 100:.3f}%;'
                        f'top:{(ly - by) / bh * 100:.3f}%;width:{lw / bw * 100:.3f}%')
            rot_attr = ""
        out.append(f'<div class="ln" style="{ln_style}"{rot_attr}>')
        for s in line["spans"]:
            color = _css_color(s["color"], s.get("alpha", 255))
            style = (f'font-size:{s["size"] / page_w * 100:.3f}cqw;'
                     f'font-family:{s["font"]};color:{color};')
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


def _render_image(im: Dict[str, Any], w: float, h: float, asset_base: str) -> str:
    """Ảnh định vị %; nếu bị clip → cắt bằng container overflow:hidden (giữ tỉ lệ)."""
    fx, fy, fw, fh = im["bbox"]
    name = im.get("name", "")
    if not name:
        return ""
    src = f"{asset_base}/{name}" if asset_base else name
    clip = im.get("clip")
    if clip:
        cx, cy, cw, ch = clip
        cw = max(cw, 1.0); ch = max(ch, 1.0)
        return (
            f'<div style="position:absolute;overflow:hidden;'
            f'left:{cx / w * 100:.3f}%;top:{cy / h * 100:.3f}%;'
            f'width:{cw / w * 100:.3f}%;height:{ch / h * 100:.3f}%">'
            f'<img src="{_esc(src)}" style="position:absolute;'
            f'left:{(fx - cx) / cw * 100:.3f}%;top:{(fy - cy) / ch * 100:.3f}%;'
            f'width:{fw / cw * 100:.3f}%;height:{fh / ch * 100:.3f}%"></div>')
    return (f'<img src="{_esc(src)}" style="left:{fx / w * 100:.3f}%;'
            f'top:{fy / h * 100:.3f}%;width:{fw / w * 100:.3f}%;height:{fh / h * 100:.3f}%">')


def block_source_text(blk: Dict[str, Any]) -> str:
    """Văn bản nguồn của block = nối text mọi span theo dòng (khoá tra TM/dịch)."""
    return " ".join(s["text"] for line in blk["lines"] for s in line["spans"]).strip()


def _render_block_translated(blk: Dict[str, Any], px: float, py: float, pw: float,
                             ph: float, page_w: float, lang_map: Dict[str, str]) -> str:
    """Dịch mode: 1 block = 1 div định vị tại bbox; text dịch WRAP trong khung
    (font/màu từ span đầu). Bản dịch dài/ngắn khác → tự xuống dòng, không méo."""
    bx, by, bw, _bh = blk["bbox"]
    spans = [s for line in blk["lines"] for s in line["spans"]]
    src = block_source_text(blk)
    txt = (lang_map or {}).get(src) or src
    s0 = spans[0] if spans else {}
    left = (bx - px) / max(pw, 1.0) * 100
    top = (by - py) / max(ph, 1.0) * 100
    width = bw / max(pw, 1.0) * 100
    fs = (s0.get("size", 12.0)) / page_w * 100
    style = (f'left:{left:.3f}%;top:{top:.3f}%;width:{width:.3f}%;'
             f'font-size:{fs:.3f}cqw;color:{s0.get("color", "#000")};'
             f'font-family:{s0.get("font", "sans-serif")};line-height:1.25')
    if s0.get("bold"):
        style += ";font-weight:bold"
    if s0.get("italic"):
        style += ";font-style:italic"
    return f'<div class="tb" style="{style}">{_esc(txt)}</div>'


def render_analyzed_page(t: Dict[str, Any], asset_base: str = "",
                         lang_map: Optional[Dict[str, str]] = None) -> str:
    """section định vị relative TRANG; block định vị thật. Khi `lang_map` (Dịch):
    mỗi block render text ĐÃ DỊCH wrap trong khung (cùng nền raster đã bỏ text)."""
    w = t.get("page_w") or 900.0
    h = t.get("page_h") or 1260.0
    if w <= 0:
        w = 900.0
    parts: List[str] = [f'<div class="pf" style="aspect-ratio:{w:.2f}/{h:.2f}">']

    bg = t.get("bg")
    if bg:
        # HYBRID: nền raster = mọi đồ hoạ (ảnh+vector+logo+icon+gradient, đã bỏ text)
        # → trung thực 100%; text HTML thật phủ lên trên.
        src = f"{asset_base}/{bg}" if (asset_base and "://" not in bg) else bg
        parts.append(f'<img class="bg" src="{_esc(src)}" '
                     f'style="position:absolute;inset:0;width:100%;height:100%">')
    else:
        # (fallback) dựng lại vector + ảnh theo đúng Z-ORDER content-stream.
        paints = []
        for d in t.get("drawings", []):
            od = d.get("order")
            paints.append((od if od is not None else -1, 0, d))
        for im in t.get("images", []):
            od = im.get("order")
            paints.append((od if od is not None else 10 ** 9, 1, im))
        paints.sort(key=lambda p: p[0])
        i = 0
        while i < len(paints):
            if paints[i][1] == 0:                   # gộp vector liền kề thành 1 svg
                grp = []
                while i < len(paints) and paints[i][1] == 0:
                    grp.append(paints[i][2]); i += 1
                svg = _vector_svg(grp, w, h)
                if svg:
                    parts.append(svg)
            else:
                parts.append(_render_image(paints[i][2], w, h, asset_base))
                i += 1

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
                    if lang_map is not None:
                        parts.append(_render_block_translated(b, cx, cy, cw, ch, w, lang_map))
                    else:
                        parts.append(_render_block_at(b, cx, cy, cw, ch, w))
                parts.append('</div>')
        else:
            for b in sec["blocks"]:
                if lang_map is not None:
                    parts.append(_render_block_translated(b, sx, sy, sw, sh, w, lang_map))
                else:
                    parts.append(_render_block_at(b, sx, sy, sw, sh, w))
        parts.append('</div>')

    parts.append('</div>')
    return "".join(parts)


# Co mỗi dòng khít bề rộng gốc: font web (Arial…) rộng/hẹp khác font PDF → đo bề
# rộng text thực rồi scaleX về đúng khung (lw). Chạy khi load/fonts ready/resize.
_FIT_SCRIPT = """<script>(function(){
function fit(){var l=document.querySelectorAll('.pf .ln');for(var i=0;i<l.length;i++){
var e=l[i];var base=e.getAttribute('data-base')||'';
e.style.transform=base;var b=e.clientWidth,t=e.scrollWidth;
if(b>2&&t>2){var r=b/t;if(r<0.5)r=0.5;if(r>2)r=2;
if(Math.abs(r-1)>0.01)e.style.transform=base+(base?' ':'')+'scaleX('+r.toFixed(4)+')';}}}
if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fit);
window.addEventListener('load',fit);
window.addEventListener('resize',function(){clearTimeout(window.__ft);window.__ft=setTimeout(fit,150);});
})();</script>"""


def render_analyzed_flow(trees: List[Dict[str, Any]], asset_base: str = "",
                         lang_map: Optional[Dict[str, str]] = None) -> str:
    """Nhiều trang xếp dọc → 1 tài liệu HTML responsive. `lang_map` (Dịch) → render
    text đã dịch theo block."""
    body = "\n".join(render_analyzed_page(t, asset_base, lang_map) for t in trees)
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<style>{_FLOW_CSS}</style></head><body>{body}{_FIT_SCRIPT}</body></html>")
