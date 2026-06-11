"""Phân tích bố cục trang → cây cấu trúc để hiển thị đẹp & quan hệ tương đối:

  page → sections (NỐI TIẾP theo thứ tự đọc, định vị relative với TRANG)
         ├─ "full"  : block chiếm gần trọn bề ngang (heading/đoạn full-width)
         └─ "band"  : dải nhiều CỘT (LỒNG NHAU) — mỗi cột định vị relative với band,
                      block trong cột xếp NỐI TIẾP (relative với cột)

Mỗi node mang bbox (điểm PDF). Renderer dùng để đặt vị trí tương đối parent/trang."""
from typing import List, Dict, Any


def _union(boxes: List[List[float]]) -> List[float]:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


def _cluster_columns(blocks: List[Dict[str, Any]], gutter_min: float) -> List[List[Dict[str, Any]]]:
    """Gom block thành các CỘT trái→phải theo khoảng trống dọc (gutter) giữa các
    khoảng x. Trả list cột (mỗi cột là list block)."""
    items = sorted(blocks, key=lambda b: b["bbox"][0])
    cols: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    cur_x1 = None
    for b in items:
        x0 = b["bbox"][0]
        x1 = x0 + b["bbox"][2]
        if cur_x1 is None or x0 <= cur_x1 + gutter_min:
            cur.append(b)
            cur_x1 = max(cur_x1 or x1, x1)
        else:
            cols.append(cur)
            cur = [b]
            cur_x1 = x1
    if cur:
        cols.append(cur)
    return cols


def analyze_layout(el: Dict[str, Any]) -> Dict[str, Any]:
    """build_blocks output → cây section/band/cột. images + drawings giữ ở mức trang."""
    page_w = el.get("page_w") or 900.0
    page_h = el.get("page_h") or 1260.0
    blocks = [{"bbox": list(b["bbox"]), "lines": b["lines"]} for b in el.get("blocks", [])]

    sections: List[Dict[str, Any]] = []
    if blocks:
        content = _union([b["bbox"] for b in blocks])
        content_w = max(content[2], 1.0)
        full_w_th = 0.62 * content_w          # >= 62% bề ngang content = full-width
        gutter_min = 0.035 * page_w           # khe cột tối thiểu

        ordered = sorted(blocks, key=lambda b: (round(b["bbox"][1]), b["bbox"][0]))
        band: List[Dict[str, Any]] = []

        def flush_band():
            if not band:
                return
            cols = _cluster_columns(band, gutter_min)
            bbox = _union([b["bbox"] for b in band])
            if len(cols) >= 2:
                sections.append({
                    "kind": "band", "bbox": bbox,
                    "columns": [{"bbox": _union([b["bbox"] for b in c]),
                                 "blocks": sorted(c, key=lambda b: b["bbox"][1])}
                                for c in cols],
                })
            else:
                sections.append({
                    "kind": "full", "bbox": bbox,
                    "blocks": sorted(band, key=lambda b: b["bbox"][1]),
                })
            band.clear()

        for b in ordered:
            if b["bbox"][2] >= full_w_th:
                flush_band()
                sections.append({"kind": "full", "bbox": b["bbox"], "blocks": [b]})
            else:
                band.append(b)
        flush_band()

    return {"page_w": page_w, "page_h": page_h, "sections": sections,
            "images": el.get("images", []), "drawings": el.get("drawings", [])}
