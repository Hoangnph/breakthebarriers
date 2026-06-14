"""Render PDF → HTML element THẬT, RELATIVE (responsive) giữ cấu trúc gốc.
Trang = container co giãn (aspect-ratio + container-type:inline-size); block định vị
theo %; cỡ chữ theo cqw (tương ứng bề rộng trang) → không còn absolute px cứng.
Mỗi đoạn = block, mỗi dòng giữ style span thật (font/màu/đậm-nghiêng); ảnh = <img> %."""
import html as html_lib
import re
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
.pf .tb{position:absolute;white-space:normal;overflow:hidden}
.pf .tb.toc{white-space:normal}
.pf .tb.toc .te{display:flex;align-items:baseline;gap:.35em;line-height:1.7}
.pf .tb.toc .tt{flex:0 1 auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pf .tb.toc .tl{flex:1 1 auto;min-width:1.2em;border-bottom:1px dotted currentColor;
    position:relative;top:-.28em}
.pf .tb.toc .tn{flex:0 0 auto;font-variant-numeric:tabular-nums}
.pf img{position:absolute;display:block}
.pf .vec{position:absolute;inset:0;width:100%;height:100%}
"""


# Mục lục: block dịch hay gộp NHIỀU mục "tiêu đề … số trang" (leader = chấm/tab)
# vào một khối → tách lại từng mục để render hàng có dotted-leader + số canh phải.
_TOC_ENTRY = re.compile(r'(.+?)\s*(?:\.{2,}|…+|\t+)\s*(\d{1,3})(?=\s|$)')


def _split_toc_entries(txt: str):
    """[(title, num)] nếu `txt` là chuỗi mục lục (mỗi mục = tiêu đề + leader
    chấm/tab + số). Văn xuôi thường (không leader) → [] (không nhận nhầm)."""
    out = []
    pos, covered = 0, 0
    for m in _TOC_ENTRY.finditer(txt):
        title = m.group(1).strip()
        if title:
            out.append((title, m.group(2)))
            covered += m.end() - m.start()
    # cần phủ phần lớn text → tránh nhận nhầm 1 câu kết bằng số
    if out and covered >= 0.6 * len(txt.strip()):
        return out
    return []


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


def _collect_block_tops(t: Dict[str, Any]) -> List[float]:
    """Top-Y (sorted) của MỌI block văn bản + ảnh trên trang → để 1 block dịch biết
    block kế dưới ở đâu mà KHÔNG tràn đè (room = next_top - by)."""
    tops: List[float] = []
    for sec in t.get("sections", []):
        if sec.get("kind") == "band":
            for col in sec.get("columns", []):
                for b in col.get("blocks", []):
                    tops.append(b["bbox"][1])
        else:
            for b in sec.get("blocks", []):
                tops.append(b["bbox"][1])
    for im in t.get("images", []):
        tops.append(im["bbox"][1])
    return sorted(tops)


def _render_block_translated(blk: Dict[str, Any], px: float, py: float, pw: float,
                             ph: float, page_w: float, lang_map: Dict[str, str],
                             page_h: float = 0.0,
                             obstacles: Optional[List[float]] = None) -> str:
    """Dịch mode: 1 block = 1 div định vị tại bbox; text dịch WRAP trong khung
    (font/màu từ span đầu). Bản dịch dài/ngắn khác → tự xuống dòng, không méo.

    Tiếng Việt dài hơn gốc ~30%: KHÔNG khóa cứng chiều cao hộp tiếng Anh (sẽ co
    chữ tí xíu, phá vỡ thứ bậc thị giác — vd tiêu đề bìa). Thay vào đó box cao tự
    nhiên (`height:auto`) neo tại top-left gốc, chỉ giới hạn `max-height` =
    khoảng trống tới đáy trang → giữ cỡ chữ lớn như gốc, chỉ co khi thật sự thiếu
    chỗ (fitTB)."""
    bx, by, bw, bh = blk["bbox"]
    spans = [s for line in blk["lines"] for s in line["spans"]]
    src = block_source_text(blk)
    txt = (lang_map or {}).get(src) or src
    s0 = spans[0] if spans else {}
    left = (bx - px) / max(pw, 1.0) * 100
    top = (by - py) / max(ph, 1.0) * 100
    width = bw / max(pw, 1.0) * 100
    fs = (s0.get("size", 12.0)) / page_w * 100
    # CHIỀU CAO box = khoảng cách tới block kế DƯỚI (không phải đáy trang) → tiêu
    # đề/đoạn giữ cỡ lớn lấp khoảng trống NHƯNG không tràn đè block sau. Height cố
    # định (cqw) để clientHeight ổn định cho fitTB; box trong suốt, text neo top.
    by_margin = by + max(bh * 0.5, 4.0)             # bỏ qua chính block + block cùng hàng
    next_top = page_h if page_h > 0 else by + bh
    for ot in (obstacles or ()):                    # sorted tăng dần
        if ot > by_margin:
            next_top = min(next_top, ot)
            break
    room = (next_top - by) / page_w * 100
    room = max(room, bh / page_w * 100)             # tối thiểu = chiều cao gốc
    style = (f'left:{left:.3f}%;top:{top:.3f}%;width:{width:.3f}%;'
             f'height:{room:.3f}cqw;overflow:hidden;'
             f'font-size:{fs:.3f}cqw;color:{s0.get("color", "#000")};'
             f'font-family:{s0.get("font", "sans-serif")};line-height:1.2')
    if s0.get("bold"):
        style += ";font-weight:bold"
    if s0.get("italic"):
        style += ";font-style:italic"
    # Mục lục: block gộp nhiều mục → tách thành hàng (tiêu đề + dotted leader + số
    # canh phải) cho chuẩn xuất bản, thay vì 1 đoạn dính số lộn xộn.
    entries = _split_toc_entries(txt)
    if entries:
        rows = "".join(
            f'<div class="te"><span class="tt">{_esc(t)}</span>'
            f'<span class="tl"></span><span class="tn">{_esc(n)}</span></div>'
            for t, n in entries)
        return (f'<div class="tb toc" data-fs="{fs:.3f}cqw" style="{style}">'
                f'{rows}</div>')
    # data-fs = cỡ gốc (cqw). fitTB reset font về ĐÂY (KHÔNG xóa inline → inherit
    # 16px). Cỡ chữ vốn nằm inline (không có rule CSS) nên reset='' = mất cỡ.
    return f'<div class="tb" data-fs="{fs:.3f}cqw" style="{style}">{_esc(txt)}</div>'


def render_analyzed_page(t: Dict[str, Any], asset_base: str = "",
                         lang_map: Optional[Dict[str, str]] = None) -> str:
    """section định vị relative TRANG; block định vị thật. Khi `lang_map` (Dịch):
    mỗi block render text ĐÃ DỊCH wrap trong khung (cùng nền raster đã bỏ text)."""
    w = t.get("page_w") or 900.0
    h = t.get("page_h") or 1260.0
    if w <= 0:
        w = 900.0
    parts: List[str] = [f'<div class="pf" style="aspect-ratio:{w:.2f}/{h:.2f}">']

    # Dịch: cần biết top mọi block/ảnh để 1 block không tràn đè block kế dưới.
    obstacles = _collect_block_tops(t) if lang_map is not None else None

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
                        parts.append(_render_block_translated(b, cx, cy, cw, ch, w, lang_map, h, obstacles))
                    else:
                        parts.append(_render_block_at(b, cx, cy, cw, ch, w))
                parts.append('</div>')
        else:
            for b in sec["blocks"]:
                if lang_map is not None:
                    parts.append(_render_block_translated(b, sx, sy, sw, sh, w, lang_map, h, obstacles))
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
function fitTB(){var l=document.querySelectorAll('.pf .tb');for(var i=0;i<l.length;i++){
var e=l[i];
// reset về cỡ GỐC (data-fs, đơn vị cqw) — KHÔNG xóa '' vì cỡ nằm inline, xóa sẽ
// về inherit 16px. Idempotent: lần co nhầm trước sẽ được phục hồi đúng cỡ.
e.style.fontSize=e.getAttribute('data-fs')||'';
// Guard: bỏ qua khi clientHeight quá nhỏ (cqw/layout chưa ổn định) → không
// over-shrink. Chỉ co khi text THẬT SỰ tràn khoảng trống (height=room).
if(e.clientHeight>16){var fs=parseFloat(getComputedStyle(e).fontSize),g=0;
while(e.scrollHeight>e.clientHeight+1&&fs>5&&g<60){fs*=0.95;e.style.fontSize=fs+'px';g++;}}}}
function all(){fit();fitTB();}
// chạy nhiều mốc + sau layout settle (rAF kép) để có ít nhất 1 lần chạy khi
// cqw đã resolve → cỡ chữ đúng, không kẹt ở giá trị co nhầm lúc đầu.
function sched(){requestAnimationFrame(function(){requestAnimationFrame(all);});}
if(document.fonts&&document.fonts.ready)document.fonts.ready.then(sched);
window.addEventListener('load',sched);
// gọi trực tiếp (không qua rAF) đề phòng môi trường throttle rAF → luôn có lần
// chạy sau khi layout/cqw ổn định, reset-rồi-co đúng cỡ.
setTimeout(all,350);setTimeout(all,900);setTimeout(all,1600);
window.addEventListener('resize',function(){clearTimeout(window.__ft);window.__ft=setTimeout(all,150);});
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


# ── DỊCH = reflow thông minh: giữ cấu trúc (cột/heading/ảnh, thứ tự đọc) nhưng để
#    chữ CHẢY tự nhiên (page cao tự co giãn), justify, font tương ứng — KHÔNG co/đè. ──

_REFLOW_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#8a8d91;font-family:Arial,Helvetica,sans-serif}
.dp{position:relative;width:96%;max-width:860px;margin:18px auto;background:#fff;
    container-type:inline-size;box-shadow:0 2px 10px rgba(0,0,0,.35);padding:6% 7%}
.dp h2{margin:.7em 0 .35em;line-height:1.25;font-weight:bold}
.dp p{margin:.45em 0;text-align:justify;line-height:1.5;hyphens:auto}
.dp .band{display:flex;gap:6%;align-items:flex-start}
.dp .band>.bcol{flex:1;min-width:0}
.dp figure{margin:1.1em 0;text-align:center}
.dp figure img{max-width:100%;height:auto;border-radius:2px}
"""


def _dich_block_html(blk: Dict[str, Any], lang_map: Optional[Dict[str, str]],
                     page_w: float, body_size: float) -> str:
    """1 block dịch → heading (<h2>) nếu font lớn/đậm, ngược lại đoạn justified (<p>)."""
    spans = [s for line in blk["lines"] for s in line["spans"]]
    if not spans:
        return ""
    src = block_source_text(blk)
    txt = (lang_map or {}).get(src) or src
    s0 = spans[0]
    size = s0.get("size", 12.0)
    fs = size / max(page_w, 1.0) * 100
    color = s0.get("color", "#000000")
    heading = size >= body_size * 1.18 or (s0.get("bold") and len(txt) < 80)
    tag = "h2" if heading else "p"
    style = f"font-size:{fs:.3f}cqw;color:{color}"
    if s0.get("bold"):
        style += ";font-weight:bold"
    if s0.get("italic"):
        style += ";font-style:italic"
    return f'<{tag} style="{style}">{_esc(txt)}</{tag}>'


def _page_body_size(t: Dict[str, Any]) -> float:
    sizes = []
    for sec in t.get("sections", []):
        blocks = sec.get("blocks") or [b for c in sec.get("columns", []) for b in c["blocks"]]
        for b in blocks:
            sp = [s for line in b["lines"] for s in line["spans"]]
            if sp:
                sizes.append(sp[0].get("size", 12.0))
    return sorted(sizes)[len(sizes) // 2] if sizes else 12.0


def _reflow_page(t: Dict[str, Any], lang_map: Dict[str, str], asset_base: str = "") -> str:
    """1 trang reflow (.dp): section theo thứ tự đọc, band giữ cột (flex), ảnh inline."""
    w = t.get("page_w") or 900.0
    body = _page_body_size(t)
    items = [(s["bbox"][1], "sec", s) for s in t.get("sections", [])]
    for im in t.get("images", []):
        if im.get("name"):
            items.append((im["bbox"][1], "img", im))
    items.sort(key=lambda x: x[0])
    parts = ['<div class="dp">']
    for _, kind, it in items:
        if kind == "img":
            name = it["name"]
            src = f"{asset_base}/{name}" if (asset_base and "://" not in name) else name
            parts.append(f'<figure><img src="{_esc(src)}" alt=""></figure>')
        elif it.get("kind") == "band":
            parts.append('<div class="band">')
            for col in it["columns"]:
                parts.append('<div class="bcol">')
                for b in col["blocks"]:
                    parts.append(_dich_block_html(b, lang_map, w, body))
                parts.append('</div>')
            parts.append('</div>')
        else:
            for b in it.get("blocks", []):
                parts.append(_dich_block_html(b, lang_map, w, body))
    parts.append('</div>')
    return "".join(parts)


def is_design_page(t: Dict[str, Any]) -> bool:
    """Trang 'design' = có ảnh nền chiếm >55% diện tích trang (bìa, TOC, banner full).
    Các trang này KHÔNG hợp reflow → render positioned (nền + text dịch đè đúng vị trí)."""
    pw = (t.get("page_w") or 1.0)
    ph = (t.get("page_h") or 1.0)
    page_area = max(pw * ph, 1.0)
    for im in t.get("images", []):
        _, _, iw, ih = im["bbox"]
        if (iw * ih) / page_area > 0.55:
            return True
    return False


def render_dich_mixed(pages: List[Dict[str, Any]], lang_map: Dict[str, str],
                      asset_base: str = "") -> str:
    """DỊCH thông minh per-page: trang design → positioned (nền raster + text dịch đè,
    .pf); trang nội dung → reflow (.dp justified). Một tài liệu, cả 2 CSS + fit script."""
    page_html = []
    for t in pages:
        if t.get("bg"):                                  # design page → positioned overlay
            page_html.append(render_analyzed_page(t, asset_base, lang_map))
        else:                                            # content page → reflow
            page_html.append(_reflow_page(t, lang_map, asset_base))
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<style>{_FLOW_CSS}{_REFLOW_CSS}</style></head>"
        f"<body>{''.join(page_html)}{_FIT_SCRIPT}</body></html>")


def render_translated_reflow(trees: List[Dict[str, Any]], lang_map: Dict[str, str],
                             asset_base: str = "") -> str:
    """Tất cả trang reflow (dùng cho test/đường thuần reflow)."""
    body = "".join(_reflow_page(t, lang_map, asset_base) for t in trees)
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<style>{_REFLOW_CSS}</style></head><body>{body}{_FIT_SCRIPT}</body></html>")
