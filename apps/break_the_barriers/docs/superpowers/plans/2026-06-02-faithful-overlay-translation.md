# Faithful Overlay Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiển thị bản dịch giữ trung thực nền/ảnh/hoạ tiết trang PDF gốc bằng ảnh raster trang làm nền + lớp text dịch định vị tuyệt đối, không thay engine dịch V2.

**Architecture:** Bật Docling `generate_page_images` để render mỗi trang thành ảnh PNG (giữ nền/ảnh). Trong cùng pass, thu bbox + span_id mỗi khối text vào sidecar `layout.json`, router lưu vào `DBPage.layout_json`. Engine V2 dịch khối như cũ. Khi phục vụ `/pages/{n}`, `overlay_renderer` ghép ảnh nền + `<div>` text dịch theo toạ độ %; `lang=en` trả raster gốc, `lang=vi` trả overlay.

**Tech Stack:** FastAPI, SQLAlchemy, Docling (docling_core BoundingBox/PageItem), Pillow, pytest.

**Điều chỉnh so với spec:** Spec nêu `pdftoppm`; máy chỉ có `pdftohtml`, nên dùng **Docling-native page image** (`generate_page_images=True`, `images_scale=2.0`) — không phụ thuộc binary ngoài, cùng một pass extract. Mọi mục tiêu/luồng khác giữ nguyên.

**Lệnh test (cwd = `apps/break_the_barriers/backend`):** `.venv/bin/pytest`

---

## File Structure

| File | Trách nhiệm | Tạo/Sửa |
|------|-------------|---------|
| `backend/scripts/migrate_overlay.sql` | Migration thêm cột `layout_json` | Tạo |
| `backend/app/models_db.py` | Thêm `DBPage.layout_json` | Sửa |
| `backend/app/services/page_image.py` | Lưu ảnh trang (PIL→PNG) + sampling màu nền | Tạo |
| `backend/app/services/extractor.py` | Bật page image; `_items_to_page_html`→(html, blocks); ghi sidecar `layout.json` + `page-{n}.png` | Sửa |
| `backend/app/routers/extraction.py` | Đọc sidecar `*.layout.json` → `DBPage.layout_json` | Sửa |
| `backend/app/services/overlay_renderer.py` | Ghép `layout_json` + translations → HTML positioned | Tạo |
| `backend/app/routers/documents.py` | `/pages/{n}`: `lang=en`→raster, `lang=vi`→overlay | Sửa |
| `backend/tests/test_overlay.py` | Test page_image + overlay_renderer + extractor blocks | Tạo |
| `backend/tests/test_api.py` | Test endpoint overlay/raster | Sửa |

**`layout_json` schema (bbox theo điểm PDF, gốc trên-trái, `[left, top, width, height]`):**
```json
{"page_w": 595.0, "page_h": 842.0, "image": "page-3.png",
 "blocks": [{"span_id": "s1", "bbox": [72.0, 40.0, 200.0, 24.0], "bg": "#ffffff"}]}
```
`image: null` hoặc `blocks: []` ⇒ trang không có raster → fallback HTML flow cũ.

---

## Phase 1 — Capture layout + page raster

### Task 1: Thêm cột `DBPage.layout_json`

**Files:**
- Create: `backend/scripts/migrate_overlay.sql`
- Modify: `backend/app/models_db.py` (class `DBPage`, sau dòng `translation_quality = Column(Float, nullable=True)`)
- Test: `backend/tests/test_overlay.py`

- [ ] **Step 1: Tạo migration SQL**

Tạo `backend/scripts/migrate_overlay.sql`:
```sql
-- Faithful Overlay Translation migration
-- Run against: postgresql://postgres:postgres@localhost:5432/break_the_barriers
ALTER TABLE pages ADD COLUMN IF NOT EXISTS layout_json TEXT;
```

- [ ] **Step 2: Viết test thất bại**

Tạo `backend/tests/test_overlay.py`:
```python
import json


def test_dbpage_has_layout_json_column(db_session):
    from backend.app.models_db import DBPage, DBDocument
    db_session.add(DBDocument(id="ov_doc", filename="x.pdf", total_pages=1, status="extracted"))
    db_session.commit()
    payload = json.dumps({"page_w": 595.0, "page_h": 842.0, "image": "page-1.png", "blocks": []})
    db_session.add(DBPage(document_id="ov_doc", page_num=1, original_html="<p>x</p>",
                          status="extracted", layout_json=payload))
    db_session.commit()
    page = db_session.query(DBPage).filter(DBPage.document_id == "ov_doc").first()
    assert json.loads(page.layout_json)["image"] == "page-1.png"
```

- [ ] **Step 3: Chạy test, xác nhận FAIL**

Run: `.venv/bin/pytest tests/test_overlay.py::test_dbpage_has_layout_json_column -v`
Expected: FAIL — `TypeError: 'layout_json' is an invalid keyword argument for DBPage`.

- [ ] **Step 4: Thêm cột vào model**

Trong `backend/app/models_db.py`, class `DBPage`, ngay sau dòng `translation_quality = Column(Float, nullable=True)`:
```python
    layout_json         = Column(Text, nullable=True)
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `.venv/bin/pytest tests/test_overlay.py::test_dbpage_has_layout_json_column -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/migrate_overlay.sql backend/app/models_db.py backend/tests/test_overlay.py
git commit -m "feat(overlay): add DBPage.layout_json column + migration"
```

---

### Task 2: Module `page_image.py` (lưu ảnh + sampling màu nền)

**Files:**
- Create: `backend/app/services/page_image.py`
- Test: `backend/tests/test_overlay.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_overlay.py`:
```python
def test_save_and_sample_bg_color(tmp_path):
    from PIL import Image
    from backend.app.services.page_image import save_page_image, sample_bg_color

    img = Image.new("RGB", (100, 50), (10, 20, 30))  # màu biết trước
    fname = save_page_image(img, str(tmp_path), "doc1", 7)
    assert fname == "page-7.png"
    assert (tmp_path / "page-7.png").exists()

    color = sample_bg_color(str(tmp_path / "page-7.png"), (0, 0, 100, 50))
    assert color == "#0a141e"  # (10,20,30) hex


def test_sample_bg_color_missing_file_defaults_white():
    from backend.app.services.page_image import sample_bg_color
    assert sample_bg_color("/nonexistent/x.png", (0, 0, 10, 10)) == "#ffffff"
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `.venv/bin/pytest tests/test_overlay.py -k "bg_color" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.services.page_image'`.

- [ ] **Step 3: Viết implementation**

Tạo `backend/app/services/page_image.py`:
```python
import os
import logging
from PIL import Image

logger = logging.getLogger(__name__)


def save_page_image(pil_image, output_dir: str, doc_id: str, page_no: int) -> str:
    """Save a PIL page image as PNG into output_dir. Returns the filename only."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"page-{page_no}.png"
    pil_image.convert("RGB").save(os.path.join(output_dir, filename), "PNG")
    return filename


def sample_bg_color(image_path: str, bbox_px) -> str:
    """Median RGB of the bbox border pixels as '#rrggbb'. Any failure → '#ffffff'."""
    try:
        l, t, r, b = (int(round(v)) for v in bbox_px)
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            l = max(0, min(l, w - 1)); r = max(l + 1, min(r, w))
            t = max(0, min(t, h - 1)); b = max(t + 1, min(b, h))
            pts = []
            sx = max(1, (r - l) // 20)
            sy = max(1, (b - t) // 20)
            for x in range(l, r, sx):
                pts.append(im.getpixel((x, t)))
                pts.append(im.getpixel((x, b - 1)))
            for y in range(t, b, sy):
                pts.append(im.getpixel((l, y)))
                pts.append(im.getpixel((r - 1, y)))
            if not pts:
                return "#ffffff"
            mid = len(pts) // 2
            rr = sorted(p[0] for p in pts)[mid]
            gg = sorted(p[1] for p in pts)[mid]
            bb = sorted(p[2] for p in pts)[mid]
            return f"#{rr:02x}{gg:02x}{bb:02x}"
    except Exception as e:
        logger.warning(f"sample_bg_color failed for {image_path}: {e}")
        return "#ffffff"
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `.venv/bin/pytest tests/test_overlay.py -k "bg_color" -v`
Expected: PASS (2 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/page_image.py backend/tests/test_overlay.py
git commit -m "feat(overlay): page_image helpers (save PNG + sample bg color)"
```

---

### Task 3: Extractor sinh ảnh trang + sidecar `layout.json`

**Files:**
- Modify: `backend/app/services/extractor.py` (`DoclingExtractor._get_converter` ~line 274; `extract_pdf_to_html` ~line 287; `_items_to_page_html` ~line 318)
- Modify: `backend/app/routers/extraction.py` (`_perform_extraction`, vòng lặp tạo `DBPage` ~line 88-108)
- Test: `backend/tests/test_overlay.py`

- [ ] **Step 1: Viết test thất bại cho `_items_to_page_html` trả (html, blocks)**

Thêm vào `backend/tests/test_overlay.py`:
```python
def test_items_to_page_html_returns_html_and_blocks():
    from types import SimpleNamespace
    from docling_core.types.doc import BoundingBox, CoordOrigin
    from backend.app.services.extractor import DoclingExtractor

    bbox = BoundingBox(l=72.0, t=40.0, r=272.0, b=64.0, coord_origin=CoordOrigin.TOPLEFT)
    item = SimpleNamespace(text="Hello world", label="text",
                           prov=[SimpleNamespace(bbox=bbox, page_no=1)])
    page_size = SimpleNamespace(width=595.0, height=842.0)

    html, blocks = DoclingExtractor._items_to_page_html([(item, 0)], 1, page_size)

    assert '<span id="s1">' in html
    assert len(blocks) == 1
    assert blocks[0]["span_id"] == "s1"
    # top-left origin: [left, top, width, height]
    assert blocks[0]["bbox"] == [72.0, 40.0, 200.0, 24.0]
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `.venv/bin/pytest tests/test_overlay.py::test_items_to_page_html_returns_html_and_blocks -v`
Expected: FAIL — hiện `_items_to_page_html` chỉ trả `str` (không unpack được thành 2 giá trị) và thiếu tham số `page_size`.

- [ ] **Step 3: Refactor `_items_to_page_html` → trả `(html, blocks)`**

Trong `backend/app/services/extractor.py`, thay toàn bộ thân `_items_to_page_html` bằng (giữ signature thêm `page_size`):
```python
    @staticmethod
    def _items_to_page_html(items: list, page_no: int, page_size=None):
        """
        Render (DocItem, level) pairs as a self-contained HTML page AND return a
        parallel list of positioned text blocks {span_id, bbox:[l,t,w,h] top-left
        points} so the overlay renderer can place translated text over the raster.
        """
        from docling_core.types.doc import CoordOrigin

        span_counter = [0]
        blocks: List[dict] = []
        page_h = getattr(page_size, "height", None)

        def record_block(sid: str, item) -> None:
            prov = getattr(item, "prov", None)
            if not prov or page_h is None:
                return
            bb = prov[0].bbox
            tl = bb if bb.coord_origin == CoordOrigin.TOPLEFT else bb.to_top_left_origin(page_height=page_h)
            blocks.append({"span_id": sid, "bbox": [tl.l, tl.t, tl.r - tl.l, tl.b - tl.t]})

        def wrap(text: str, item=None) -> str:
            span_counter[0] += 1
            sid = f"s{span_counter[0]}"
            if item is not None:
                record_block(sid, item)
            return f'<span id="{sid}">{html_lib.escape(text)}</span>'

        body_parts: List[str] = []
        open_list = False

        for item, level in items:
            text: str = getattr(item, "text", "") or ""
            label: str = str(getattr(item, "label", "text"))

            if label == "list_item":
                if not open_list:
                    body_parts.append("<ul>")
                    open_list = True
                body_parts.append(f"  <li>{wrap(text, item)}</li>")
                continue

            if open_list:
                body_parts.append("</ul>")
                open_list = False

            if not text and label not in ("picture",):
                continue

            if label == "section_header":
                h = min(max(level + 1, 2), 6)
                body_parts.append(f"<h{h}>{wrap(text, item)}</h{h}>")
            elif label == "code":
                body_parts.append(f"<pre><code>{html_lib.escape(text)}</code></pre>")
            elif label == "picture":
                body_parts.append(f'<figure><img src="" alt="Figure on page {page_no}"/></figure>')
            elif label == "table":
                body_parts.append(DoclingExtractor._table_text_to_html(text))
            else:
                body_parts.append(f"<p>{wrap(text, item)}</p>")

        if open_list:
            body_parts.append("</ul>")

        html = (
            f"<!DOCTYPE html>\n<html>\n<head>\n"
            f'<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"<style>\n{_DOCLING_RESPONSIVE_CSS}\n</style>\n"
            f"</head>\n<body>\n"
            + "\n".join(body_parts)
            + "\n</body>\n</html>"
        )
        return html, blocks
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `.venv/bin/pytest tests/test_overlay.py::test_items_to_page_html_returns_html_and_blocks -v`
Expected: PASS

- [ ] **Step 5: Bật page image trong converter**

Trong `backend/app/services/extractor.py`, `DoclingExtractor._get_converter`, ngay sau dòng tạo `pipeline_options = PdfPipelineOptions()`:
```python
                pipeline_options.generate_page_images = True
                pipeline_options.images_scale = 2.0
```

- [ ] **Step 6: Sinh ảnh + sidecar layout.json trong `extract_pdf_to_html`**

Trong `backend/app/services/extractor.py`, đầu file thêm import:
```python
import json
from backend.app.services.page_image import save_page_image, sample_bg_color
```
Thay vòng lặp ghi file trong `extract_pdf_to_html` (đoạn `for page_no in sorted(pages_items.keys()): ... html_files.append(file_path)`) bằng:
```python
        html_files = []
        for page_no in sorted(pages_items.keys()):
            page_item = doc.pages.get(page_no)
            page_size = page_item.size if page_item else None
            page_html, blocks = cls._items_to_page_html(pages_items[page_no], page_no, page_size)

            file_path = os.path.normpath(os.path.join(output_dir, f"{doc_id}-{page_no}.html"))
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(page_html)
            html_files.append(file_path)

            # Render the page raster + build the positioned layout sidecar.
            image_name = None
            pil_img = page_item.image.pil_image if (page_item and page_item.image) else None
            if pil_img is not None and page_size is not None:
                image_name = save_page_image(pil_img, output_dir, doc_id, page_no)
                img_path = os.path.join(output_dir, image_name)
                scale_x = pil_img.width / page_size.width
                scale_y = pil_img.height / page_size.height
                for blk in blocks:
                    l, t, w, h = blk["bbox"]
                    bbox_px = (l * scale_x, t * scale_y, (l + w) * scale_x, (t + h) * scale_y)
                    blk["bg"] = sample_bg_color(img_path, bbox_px)

            layout = {
                "page_w": page_size.width if page_size else None,
                "page_h": page_size.height if page_size else None,
                "image": image_name,
                "blocks": blocks if image_name else [],
            }
            layout_path = os.path.normpath(os.path.join(output_dir, f"{doc_id}-{page_no}.layout.json"))
            with open(layout_path, "w", encoding="utf-8") as f:
                json.dump(layout, f)

        return html_files
```

- [ ] **Step 7: Router đọc sidecar → `DBPage.layout_json`**

Trong `backend/app/routers/extraction.py`, `_perform_extraction`, trong vòng `for i, file_path in enumerate(html_files):`, ngay trước dòng `db.add(DBPage(...))`:
```python
            layout_json = None
            layout_path = file_path[:-5] + ".layout.json"  # ".html" -> ".layout.json"
            if os.path.exists(layout_path):
                with open(layout_path, "r", encoding="utf-8") as lf:
                    layout_json = lf.read()
```
Và sửa dòng tạo `DBPage` để truyền cột mới:
```python
            db.add(DBPage(document_id=doc_id, page_num=page_num, original_html=final_html,
                          status="raw", layout_json=layout_json))
```

- [ ] **Step 8: Chạy toàn bộ test, xác nhận PASS**

Run: `.venv/bin/pytest tests/ -q`
Expected: tất cả PASS (131 cũ + test mới). Không trang nào lỗi do cột mới nullable.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/extractor.py backend/app/routers/extraction.py backend/tests/test_overlay.py
git commit -m "feat(overlay): render page raster + capture positioned layout sidecar"
```

---

## Phase 2 — Overlay renderer + serving

### Task 4: Module `overlay_renderer.py`

**Files:**
- Create: `backend/app/services/overlay_renderer.py`
- Test: `backend/tests/test_overlay.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_overlay.py`:
```python
def test_render_overlay_html_positions_translated_text():
    from backend.app.services.overlay_renderer import render_overlay_html
    layout = {"page_w": 1000.0, "page_h": 2000.0, "image": "page-1.png",
              "blocks": [{"span_id": "s1", "bbox": [100.0, 200.0, 300.0, 50.0], "bg": "#ffffff"}]}
    html = render_overlay_html(layout, {"s1": "Xin chào"}, "/api/docs/d1/assets")

    assert 'src="/api/docs/d1/assets/page-1.png"' in html
    assert "Xin chào" in html
    assert "left:10.000%" in html   # 100/1000
    assert "top:10.000%" in html    # 200/2000
    assert "width:30.000%" in html  # 300/1000


def test_render_overlay_empty_translations_is_raster_only():
    from backend.app.services.overlay_renderer import render_overlay_html
    layout = {"page_w": 1000.0, "page_h": 2000.0, "image": "page-1.png",
              "blocks": [{"span_id": "s1", "bbox": [100.0, 200.0, 300.0, 50.0], "bg": "#ffffff"}]}
    html = render_overlay_html(layout, {}, "/api/docs/d1/assets")
    assert 'src="/api/docs/d1/assets/page-1.png"' in html
    assert "ov-text" not in html  # không có hộp text khi không có bản dịch


def test_render_overlay_escapes_html():
    from backend.app.services.overlay_renderer import render_overlay_html
    layout = {"page_w": 100.0, "page_h": 100.0, "image": "p.png",
              "blocks": [{"span_id": "s1", "bbox": [0, 0, 100, 20], "bg": "#fff"}]}
    html = render_overlay_html(layout, {"s1": "<b>x</b>"}, "/base")
    assert "&lt;b&gt;x&lt;/b&gt;" in html
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `.venv/bin/pytest tests/test_overlay.py -k overlay_html -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.services.overlay_renderer'`.

- [ ] **Step 3: Viết implementation**

Tạo `backend/app/services/overlay_renderer.py`:
```python
import html as html_lib
import math

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
        l, t, w, h = blk["bbox"]
        left = l / pw * 100.0
        top = t / ph * 100.0
        width = w / pw * 100.0
        bg = blk.get("bg", "#ffffff")
        fs = _fit_font_size(text, w, h)
        parts.append(
            f'<div class="ov-text" style="left:{left:.3f}%;top:{top:.3f}%;'
            f'width:{width:.3f}%;background:{bg};color:{_text_color(bg)};'
            f'font-size:{fs:.1f}px;">{html_lib.escape(text)}</div>'
        )

    img_tag = f'<img class="ov-bg" src="{image_url_base}/{image}" alt="page"/>' if image else ""
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<style>{_OVERLAY_CSS}</style></head><body>"
        f'<div class="ov-page">{img_tag}{"".join(parts)}</div>'
        "</body></html>"
    )
```

Lưu ý font-size dùng đơn vị px trong không gian điểm-trang; vì container scale theo % nên cỡ chữ co giãn cùng ảnh nền (đủ chính xác cho v1).

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `.venv/bin/pytest tests/test_overlay.py -k overlay_html -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/overlay_renderer.py backend/tests/test_overlay.py
git commit -m "feat(overlay): overlay_renderer (raster bg + positioned translated text)"
```

---

### Task 5: Wire `/pages/{page_num}` dùng raster/overlay

**Files:**
- Modify: `backend/app/routers/documents.py` (`get_page_content`, nhánh `lang` ~line 247-260)
- Test: `backend/tests/test_overlay.py`

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_overlay.py`:
```python
def test_pages_endpoint_uses_overlay_when_layout_present(client, db_session):
    import json
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="ovapi", filename="x.pdf", total_pages=1, status="translated"))
    layout = {"page_w": 1000.0, "page_h": 2000.0, "image": "page-1.png",
              "blocks": [{"span_id": "s1", "bbox": [100.0, 200.0, 300.0, 50.0], "bg": "#ffffff"}]}
    db_session.add(DBPage(document_id="ovapi", page_num=1, original_html="<p>orig</p>",
                          status="translated", layout_json=json.dumps(layout)))
    db_session.add(DBTranslation(document_id="ovapi", page_num=1, span_id="s1",
                                 original_text="Hello", translated_text="Xin chào"))
    db_session.commit()

    vi = client.get("/api/docs/ovapi/pages/1?lang=vi").json()
    assert "Xin chào" in vi["html"]
    assert "page-1.png" in vi["html"]

    en = client.get("/api/docs/ovapi/pages/1?lang=en").json()
    assert "page-1.png" in en["html"]      # raster gốc
    assert "Xin chào" not in en["html"]     # không overlay text khi lang=en


def test_pages_endpoint_falls_back_without_layout(client, db_session):
    from backend.app.models_db import DBDocument, DBPage
    db_session.add(DBDocument(id="noov", filename="x.pdf", total_pages=1, status="extracted"))
    db_session.add(DBPage(document_id="noov", page_num=1, original_html="<p>orig-en</p>",
                          translated_html="<p>dich-vi</p>", status="translated", layout_json=None))
    db_session.commit()
    assert "orig-en" in client.get("/api/docs/noov/pages/1?lang=en").json()["html"]
    assert "dich-vi" in client.get("/api/docs/noov/pages/1?lang=vi").json()["html"]
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `.venv/bin/pytest tests/test_overlay.py -k pages_endpoint -v`
Expected: FAIL — `lang=vi` trả `dich`/compile cũ (không có `page-1.png`); `lang=en` trả `original_html` (không có raster).

- [ ] **Step 3: Sửa endpoint dùng layout_json**

Trong `backend/app/routers/documents.py`, `get_page_content`, thay khối:
```python
    if lang == "en":
        html = page.original_html
    else:
        if page.translated_html:
            html = page.translated_html
        else:
            translations = db.query(DBTranslation).filter(
                DBTranslation.document_id == doc_id,
                DBTranslation.page_num == page_num
            ).all()
            trans_dict = {}
            for t in translations:
                trans_dict[t.span_id] = t.translated_text or Translator.translate_text_agentic(t.original_text)
            html = Compiler.inject_translation(page.original_html, trans_dict)
```
bằng:
```python
    import json as _json
    from backend.app.services.overlay_renderer import render_overlay_html

    layout = None
    if page.layout_json:
        try:
            parsed = _json.loads(page.layout_json)
            if parsed.get("image"):
                layout = parsed
        except Exception:
            layout = None
    image_base = f"/api/docs/{doc_id}/assets"

    if lang == "en":
        if layout:
            html = render_overlay_html(layout, {}, image_base)   # raster gốc, không overlay
        else:
            html = page.original_html
    else:
        translations = db.query(DBTranslation).filter(
            DBTranslation.document_id == doc_id,
            DBTranslation.page_num == page_num
        ).all()
        if layout:
            trans_dict = {t.span_id: (t.translated_text or "") for t in translations}
            html = render_overlay_html(layout, trans_dict, image_base)
        elif page.translated_html:
            html = page.translated_html
        else:
            trans_dict = {}
            for t in translations:
                trans_dict[t.span_id] = t.translated_text or Translator.translate_text_agentic(t.original_text)
            html = Compiler.inject_translation(page.original_html, trans_dict)
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `.venv/bin/pytest tests/test_overlay.py -k pages_endpoint -v`
Expected: PASS (2 test)

- [ ] **Step 5: Chạy toàn bộ test, xác nhận không hồi quy**

Run: `.venv/bin/pytest tests/ -q`
Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/documents.py backend/tests/test_overlay.py
git commit -m "feat(overlay): serve raster (lang=en) and overlay (lang=vi) from layout_json"
```

---

## Phase 3 — Integration verification

### Task 6: Integration test với PDF thật + ghi nhận giới hạn

**Files:**
- Test: `backend/tests/test_overlay.py`
- Modify: `apps/break_the_barriers/docs/superpowers/specs/2026-06-02-faithful-overlay-translation-design.md` (thêm mục "Implementation Notes")

- [ ] **Step 1: Viết integration test (Docling + Pillow thật, không gọi Gemini)**

Thêm vào `backend/tests/test_overlay.py`:
```python
import os
import pytest

_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
       "assets", "books", "2024-wttc-introduction-to-ai.pdf"))


@pytest.mark.skipif(not os.path.exists(_PDF), reason="sample PDF not available")
def test_extract_produces_raster_and_layout(tmp_path):
    import json
    from backend.app.services.extractor import DoclingExtractor

    out = str(tmp_path / "out")
    files = DoclingExtractor.extract_pdf_to_html(_PDF, out, "wttc_it")
    assert files, "no html pages produced"

    # ít nhất 1 trang có ảnh raster + layout blocks
    layouts = [f for f in os.listdir(out) if f.endswith(".layout.json")]
    assert layouts, "no layout sidecars written"
    pngs = [f for f in os.listdir(out) if f.endswith(".png")]
    assert pngs, "no page raster images written"

    sample = json.load(open(os.path.join(out, layouts[0]), encoding="utf-8"))
    assert sample["page_w"] and sample["page_h"]
    if sample["image"]:
        assert os.path.exists(os.path.join(out, sample["image"]))
```

- [ ] **Step 2: Chạy integration test, xác nhận PASS**

Run: `.venv/bin/pytest tests/test_overlay.py::test_extract_produces_raster_and_layout -v`
Expected: PASS (Docling render ảnh + sidecar). Nếu PDF mẫu không có → test tự skip (không fail CI).

- [ ] **Step 3: Ghi Implementation Notes vào spec**

Thêm mục cuối `2026-06-02-faithful-overlay-translation-design.md`:
```markdown
## Implementation Notes

- Page raster do Docling render (`generate_page_images=True`, `images_scale=2.0`),
  KHÔNG dùng pdftoppm (binary không có trên máy). Cùng một pass extract.
- Overflow xử lý bằng auto-fit font + vertical growth (`overflow: visible`,
  không clip). Cờ `needs_review`-on-overflow tự động được hoãn (cần ghép độ
  dài bản dịch với hộp ở thời điểm dịch; ngoài scope GET phục vụ trang).
- Masking chữ gốc dùng màu sampling phẳng — chữ trên ảnh/gradient có thể thành
  "miếng vá" nhẹ (giới hạn đã biết, hiếm với body text).
```

- [ ] **Step 4: Chạy toàn bộ test cuối cùng**

Run: `.venv/bin/pytest tests/ -q`
Expected: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_overlay.py apps/break_the_barriers/docs/superpowers/specs/2026-06-02-faithful-overlay-translation-design.md
git commit -m "test(overlay): integration test (real PDF raster+layout) + impl notes"
```

---

## Self-Review (đã thực hiện)

**Spec coverage:**
- Raster nền + overlay text → Task 3 (raster+layout), Task 4 (renderer), Task 5 (serving). ✅
- Giữ engine V2 → không Task nào đụng `translator_v2.py`/bảng `translations`. ✅
- `DBPage.layout_json` + migration → Task 1. ✅
- Toạ độ %, lật trục Y → Task 3 (`to_top_left_origin`) + Task 4 (đổi %). ✅
- Masking sampling màu → Task 2 + Task 3. ✅
- Auto-fit font → Task 4 (`_fit_font_size`). ✅
- Fallback (image=null/thiếu bbox) → Task 3 (layout rỗng) + Task 5 (nhánh fallback). ✅
- `lang=en` raster / `lang=vi` overlay → Task 5. ✅
- Testing unit + integration + regression → Task 1-6. ✅

**Điều chỉnh có chủ ý so với spec (đã ghi trong Implementation Notes):**
- Dùng Docling page image thay pdftoppm.
- `needs_review`-on-overflow tự động được hoãn; thay bằng auto-fit + vertical growth.

**Type consistency:** `render_overlay_html(layout, translations, image_url_base)`, `save_page_image(pil_image, output_dir, doc_id, page_no)→filename`, `sample_bg_color(image_path, bbox_px)→hex`, `_items_to_page_html(items, page_no, page_size)→(html, blocks)`, block schema `{span_id, bbox:[l,t,w,h], bg}` — nhất quán xuyên suốt. ✅
