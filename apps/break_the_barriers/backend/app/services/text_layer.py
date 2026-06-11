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
        out.append({
            "d": "".join(cmds),
            "fill": _rgb(d["fill"]) if (d.get("fill") and dtype in ("f", "fs")) else None,
            "stroke": _rgb(d["color"]) if (d.get("color") and dtype in ("s", "fs")) else None,
            "width": d.get("width") or 0.0,
            "fill_opacity": round(float(d.get("fill_opacity", 1.0) or 1.0), 3),
            "stroke_opacity": round(float(d.get("stroke_opacity", 1.0) or 1.0), 3),
        })
    return out


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
    images = []
    for info in page.get_image_info(xrefs=True):
        if not info.get("xref"):
            continue
        bx0, by0, bx1, by1 = info["bbox"]
        images.append({"xref": info["xref"], "bbox": [bx0, by0, bx1 - bx0, by1 - by0]})
    return {"page_w": rect.width, "page_h": rect.height, "blocks": blocks,
            "images": images, "drawings": build_drawings(page)}


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
