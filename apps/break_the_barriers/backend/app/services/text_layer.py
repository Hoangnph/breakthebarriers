"""Trích text layer định vị (cho view Gốc) và reflow fallback (khi Docling lỗi)
từ PyMuPDF. Toạ độ là PDF points, gốc top-left — cùng hệ với page.get_svg_image()."""
import math
from typing import List, Dict, Any


def _hex_color(c) -> str:
    try:
        return "#%06x" % (int(c) & 0xFFFFFF)
    except Exception:
        return "#000000"


def _font_family(name: str) -> str:
    n = (name or "").lower()
    if any(k in n for k in ("times", "georgia", "serif", "minion", "garamond", "roman", "book antiqua")):
        return "Georgia, 'Times New Roman', serif"
    if any(k in n for k in ("courier", "mono", "consol")):
        return "'Courier New', monospace"
    return "Arial, Helvetica, sans-serif"


def build_elements(page) -> Dict[str, Any]:
    """Trích trang thành element HTML thật giữ layout gốc (kiểu pdf2htmlEX):
    mỗi span chữ → {bbox, text, size, font-family, color, bold, italic, baseline};
    mỗi ảnh nhúng → {xref, bbox}. Toạ độ PDF points top-left."""
    rect = page.rect
    texts: List[Dict[str, Any]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for s in line.get("spans", []):
                t = s.get("text", "")
                if not t.strip():
                    continue
                x0, y0, x1, y1 = s["bbox"]
                name = s.get("font", "") or ""
                nl = name.lower()
                flags = s.get("flags", 0)
                bold = bool(flags & 16) or any(k in nl for k in ("bold", "black", "heavy", "semibold"))
                italic = bool(flags & 2) or "italic" in nl or "oblique" in nl
                texts.append({
                    "bbox": [x0, y0, x1 - x0, y1 - y0],
                    "text": t,
                    "size": s.get("size", 0.0),
                    "font": _font_family(name),
                    "color": _hex_color(s.get("color", 0)),
                    "bold": bold,
                    "italic": italic,
                    "oy": (s.get("origin") or [x0, y1])[1],
                })
    images = []
    for info in page.get_image_info(xrefs=True):
        if not info.get("xref"):
            continue
        bx0, by0, bx1, by1 = info["bbox"]
        images.append({"xref": info["xref"], "bbox": [bx0, by0, bx1 - bx0, by1 - by0]})
    return {"page_w": rect.width, "page_h": rect.height, "texts": texts, "images": images}


def _effective_size(s: Dict[str, Any]) -> float:
    """Trích font-size từ HÌNH HỌC glyph: size = bbox_h / (ascender − descender).
    PyMuPDF cho `size` danh nghĩa, nhưng khi text bị scale bởi ma trận thì `size`
    sai — chiều cao bbox mới phản ánh cỡ THẬT. Lấy giá trị từ bbox khi lệch >5%."""
    nominal = float(s.get("size", 0.0) or 0.0)
    bb = s.get("bbox")
    span = (s.get("ascender", 0.0) or 0.0) - (s.get("descender", 0.0) or 0.0)
    if bb and span > 0.1:
        derived = (bb[3] - bb[1]) / span
        if nominal <= 0 or abs(derived - nominal) / max(nominal, 1.0) > 0.05:
            return round(derived, 2)
    return round(nominal, 2)


def _span_style(s: Dict[str, Any]) -> Dict[str, Any]:
    name = s.get("font", "") or ""
    nl = name.lower()
    flags = s.get("flags", 0)
    return {
        "text": s.get("text", ""),
        "size": _effective_size(s),
        "font": _font_family(name),
        "color": _hex_color(s.get("color", 0)),
        "alpha": int(s.get("alpha", 255)),   # độ mờ chữ 0..255 (255 = đặc)
        "bold": bool(flags & 16) or any(k in nl for k in ("bold", "black", "heavy", "semibold")),
        "italic": bool(flags & 2) or "italic" in nl or "oblique" in nl,
    }


def _rgb(c) -> str:
    """Tuple PyMuPDF (r,g,b) 0..1 → #rrggbb."""
    try:
        return "#%02x%02x%02x" % (max(0, min(255, round(c[0] * 255))),
                                  max(0, min(255, round(c[1] * 255))),
                                  max(0, min(255, round(c[2] * 255))))
    except Exception:
        return "#000000"


def build_drawings(page) -> List[Dict[str, Any]]:
    """Trích đồ hoạ vector (line/rect/curve/fill) từ page.get_drawings() → list path
    SVG: {d, fill, stroke, width}. Render thành <svg> element thật (không raster)."""
    out: List[Dict[str, Any]] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return out
    for d in drawings:
        cmds: List[str] = []
        for it in d.get("items", []):
            op = it[0]
            try:
                if op == "l":
                    p1, p2 = it[1], it[2]
                    cmds.append(f"M{p1.x:.2f} {p1.y:.2f}L{p2.x:.2f} {p2.y:.2f}")
                elif op == "c":
                    p1, p2, p3, p4 = it[1], it[2], it[3], it[4]
                    cmds.append(f"M{p1.x:.2f} {p1.y:.2f}C{p2.x:.2f} {p2.y:.2f} "
                                f"{p3.x:.2f} {p3.y:.2f} {p4.x:.2f} {p4.y:.2f}")
                elif op == "re":
                    r = it[1]
                    cmds.append(f"M{r.x0:.2f} {r.y0:.2f}H{r.x1:.2f}V{r.y1:.2f}H{r.x0:.2f}Z")
                elif op == "qu":
                    q = it[1]
                    cmds.append(f"M{q.ul.x:.2f} {q.ul.y:.2f}L{q.ur.x:.2f} {q.ur.y:.2f}"
                                f"L{q.lr.x:.2f} {q.lr.y:.2f}L{q.ll.x:.2f} {q.ll.y:.2f}Z")
            except Exception:
                continue
        if not cmds:
            continue
        dtype = d.get("type", "s")
        r = d.get("rect")
        out.append({
            "d": "".join(cmds),
            "fill": _rgb(d["fill"]) if (d.get("fill") and dtype in ("f", "fs")) else None,
            "stroke": _rgb(d["color"]) if (d.get("color") and dtype in ("s", "fs")) else None,
            "width": d.get("width") or 0.0,
            "fill_opacity": round(float(d.get("fill_opacity", 1.0) or 1.0), 3),
            "stroke_opacity": round(float(d.get("stroke_opacity", 1.0) or 1.0), 3),
            "rect": [r.x0, r.y0, r.x1, r.y1] if r is not None else None,
        })
    return out


def save_pdf_image(doc, xref: int, path: str) -> bool:
    """Lưu ảnh PDF ra PNG, ÁP soft-mask (alpha) nếu có → vùng trong suốt KHÔNG bị
    ĐEN mà lộ nền trang. CMYK/separation → RGB. Trả True nếu lưu được."""
    import fitz
    try:
        pix = fitz.Pixmap(doc, xref)
        if pix.n - pix.alpha >= 4:                 # CMYK/separation → RGB
            pix = fitz.Pixmap(fitz.csRGB, pix)
        smask = 0
        try:
            smask = doc.extract_image(xref).get("smask", 0)
        except Exception:
            smask = 0
        if smask:
            pix = fitz.Pixmap(pix, fitz.Pixmap(doc, smask))   # gắn alpha từ smask
        pix.save(path)
        return True
    except Exception:
        return False


def _assign_paint_order(page, images: List[Dict[str, Any]],
                        drawings: List[Dict[str, Any]]) -> None:
    """Gán 'order' = vị trí trong content-stream (get_bboxlog) cho ảnh & vector, để
    render đúng Z-ORDER (vd panel trắng vẽ SAU ảnh nền phải nằm TRÊN ảnh)."""
    try:
        log = page.get_bboxlog()
    except Exception:
        log = []
    used = set()

    def match(kinds, tgt):
        if not tgt:
            return None
        for gi in range(len(log)):
            if gi in used:
                continue
            k, r = log[gi]
            if any(x in k for x in kinds) and all(abs(r[i] - tgt[i]) < 2.0 for i in range(4)):
                used.add(gi)
                return gi
        return None

    for im in images:
        x, y, wv, hv = im["bbox"]
        im["order"] = match(("image",), [x, y, x + wv, y + hv])
    for d in drawings:
        d["order"] = match(("fill-path", "stroke-path", "shade", "path"), d.get("rect"))


def _soften_overlays(images: List[Dict[str, Any]], drawings: List[Dict[str, Any]]) -> None:
    """Fill ĐẶC vẽ TRÊN và phủ ≥80% một ảnh bên dưới → gần như chắc chắn là lớp
    overlay làm tối/gradient (nếu không ảnh đã vô nghĩa) → giảm opacity để ảnh xuyên qua."""
    for d in drawings:
        if not d.get("fill") or d.get("order") is None or not d.get("rect"):
            continue
        dr = d["rect"]
        for im in images:
            io = im.get("order")
            if io is None or io >= d["order"]:        # ảnh phải nằm DƯỚI fill
                continue
            ix, iy, iw, ih = im["bbox"]
            ox = max(0.0, min(dr[2], ix + iw) - max(dr[0], ix))
            oy = max(0.0, min(dr[3], iy + ih) - max(dr[1], iy))
            if ox * oy >= 0.80 * max(iw * ih, 1.0):
                d["fill_opacity"] = min(d.get("fill_opacity", 1.0), 0.5)
                break


def _clip_rects(page) -> List[List[float]]:
    """Các vùng clip (scissor) không phải full-trang — để cắt ảnh đặt quá khổ."""
    out: List[List[float]] = []
    try:
        for d in page.get_drawings(extended=True):
            if d.get("type") == "clip" and d.get("scissor"):
                sc = d["scissor"]
                out.append([sc.x0, sc.y0, sc.x1, sc.y1])
    except Exception:
        pass
    return out


def _image_clip(full_xywh: List[float], clips: List[List[float]],
                page_w: float, page_h: float):
    """Tìm vùng hiển thị THẬT của ảnh = giao bbox đặt với clip phù hợp nhất.
    Trả [x,y,w,h] khi ảnh bị clip (cần crop), None khi không."""
    ix0, iy0 = full_xywh[0], full_xywh[1]
    ix1, iy1 = ix0 + full_xywh[2], iy0 + full_xywh[3]
    iarea = max((ix1 - ix0) * (iy1 - iy0), 1.0)
    page_area = page_w * page_h
    best = None
    best_area = 0.0
    for c in clips:
        if (c[2] - c[0]) * (c[3] - c[1]) > 0.95 * page_area:   # bỏ clip ~full-trang
            continue
        nx0, ny0 = max(ix0, c[0]), max(iy0, c[1])
        nx1, ny1 = min(ix1, c[2]), min(iy1, c[3])
        if nx1 <= nx0 or ny1 <= ny0:
            continue
        area = (nx1 - nx0) * (ny1 - ny0)
        shrinks = (nx1 - nx0) < 0.98 * (ix1 - ix0) or (ny1 - ny0) < 0.98 * (iy1 - iy0)
        if shrinks and area >= 0.40 * iarea and area > best_area:
            best_area = area
            best = [nx0, ny0, nx1 - nx0, ny1 - ny0]
    return best


def build_blocks(page) -> Dict[str, Any]:
    """Gom trang thành CẤU TRÚC block (paragraph) theo PyMuPDF → mỗi block giữ
    bbox + các dòng (mỗi dòng là list span có style). Dùng để dựng HTML RELATIVE:
    block định vị %, font cqw (size tương ứng theo bề rộng trang) — responsive,
    không còn absolute px cứng. Toạ độ PDF points top-left."""
    rect = page.rect
    blocks: List[Dict[str, Any]] = []
    data = page.get_text("dict")
    for b in data.get("blocks", []):
        if b.get("type") != 0:
            continue
        x0, y0, x1, y1 = b["bbox"]
        lines: List[Dict[str, Any]] = []
        for line in b.get("lines", []):
            spans = [_span_style(s) for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            lx0, ly0, lx1, ly1 = line.get("bbox", [x0, y0, x1, y1])
            dv = line.get("dir", (1.0, 0.0))   # vector hướng chữ → góc xoay
            rot = round(math.degrees(math.atan2(dv[1], dv[0])), 2)
            lines.append({"bbox": [lx0, ly0, lx1 - lx0, ly1 - ly0], "spans": spans,
                          "rot": rot, "wmode": int(line.get("wmode", 0))})
        if lines:
            blocks.append({"bbox": [x0, y0, x1 - x0, y1 - y0], "lines": lines})
    clips = _clip_rects(page)
    images = []
    for info in page.get_image_info(xrefs=True):
        if not info.get("xref"):
            continue
        bx0, by0, bx1, by1 = info["bbox"]
        full = [bx0, by0, bx1 - bx0, by1 - by0]
        clip = _image_clip(full, clips, rect.width, rect.height)   # vùng hiển thị thật
        images.append({"xref": info["xref"], "bbox": full, "clip": clip})
    drawings = build_drawings(page)
    _assign_paint_order(page, images, drawings)                    # Z-ORDER ảnh/vector
    _soften_overlays(images, drawings)                             # overlay tối → trong suốt
    return {"page_w": rect.width, "page_h": rect.height, "blocks": blocks,
            "images": images, "drawings": drawings}


def build_text_layer(page) -> Dict[str, Any]:
    """Trả {"page_w", "page_h", "spans": [{"bbox":[x,y,w,h], "text", "size"}]}."""
    rect = page.rect
    spans: List[Dict[str, Any]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # 0 = text, 1 = image
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text.strip():
                    continue
                x0, y0, x1, y1 = span["bbox"]
                spans.append({
                    "bbox": [x0, y0, x1 - x0, y1 - y0],
                    "text": text,
                    "size": span.get("size", 0.0),
                })
    return {"page_w": rect.width, "page_h": rect.height, "spans": spans}


def reflow_blocks(page) -> List[Dict[str, Any]]:
    """Fallback reflow khi không có Docling: text blocks theo reading order với
    role heuristic (heading nếu font >= 1.2x median). Trả [{"text","bbox","role"}]."""
    items: List[Dict[str, Any]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        parts: List[str] = []
        sizes: List[float] = []
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                t = span.get("text", "")
                if t.strip():
                    parts.append(t)
                    sizes.append(span.get("size", 0.0))
        text = " ".join(parts).strip()
        if not text:
            continue
        x0, y0, x1, y1 = block["bbox"]
        median = sorted(sizes)[len(sizes) // 2] if sizes else 0.0
        items.append({"text": text, "bbox": [x0, y0, x1 - x0, y1 - y0], "size": median})
    if not items:
        return []
    body_size = sorted(it["size"] for it in items)[(len(items) - 1) // 2]
    items.sort(key=lambda b: (round(b["bbox"][1]), b["bbox"][0]))  # top→bottom, left→right
    out: List[Dict[str, Any]] = []
    for it in items:
        role = "heading" if it["size"] >= body_size * 1.2 else "body"
        out.append({"text": it["text"], "bbox": it["bbox"], "role": role})
    return out
