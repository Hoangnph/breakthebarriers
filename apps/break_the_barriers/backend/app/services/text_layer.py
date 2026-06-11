"""Trích text layer định vị (cho view Gốc) và reflow fallback (khi Docling lỗi)
từ PyMuPDF. Toạ độ là PDF points, gốc top-left — cùng hệ với page.get_svg_image()."""
from typing import List, Dict, Any


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
