# Faithful SVG Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển PDF → HTML giữ nguyên bản gốc (pixel y hệt) cho view "Gốc", reflow sạch cho view "Dịch", toggle toàn trang — thay thế cơ chế raster+overlay cũ.

**Architecture:** Mỗi trang sinh 3 sidecar: SVG trung thực (PyMuPDF `get_svg_image`), text layer JSON (vô hình, để copy), và reflow HTML (Docling, có span id để dịch). Endpoint `view=goc` ráp SVG + lớp span trong suốt; `view=dich` chèn bản dịch vào reflow HTML. Hai view độc lập, không overlay text dịch lên gốc.

**Tech Stack:** FastAPI, SQLAlchemy, PyMuPDF (fitz) 1.27, Docling (CPU), BeautifulSoup4, pytest (SQLite in-memory).

**Spec:** `docs/superpowers/specs/2026-06-10-faithful-svg-reader-design.md`

**Lưu ý môi trường:** chạy mọi lệnh từ `apps/break_the_barriers/backend`; Python = `.venv/bin/python`, test = `.venv/bin/pytest`. Đĩa đang sát hạn — dọn `data/extracted_html/<doc cũ>` nếu cần.

---

## File Structure

| File | Trạng thái | Trách nhiệm |
|---|---|---|
| `app/services/text_layer.py` | tạo mới | `build_text_layer(page)`, `reflow_blocks(page)` từ PyMuPDF |
| `app/services/faithful_extractor.py` | tạo mới | `FaithfulExtractor.extract_pdf()` sinh 3 sidecar/trang |
| `app/services/faithful_renderer.py` | tạo mới | `render_faithful_page()` ráp HTML view Gốc |
| `app/models_db.py` | sửa | thêm 2 cột `DBPage.svg_path`, `text_layer_json` |
| `app/routers/extraction.py` | sửa | dùng `FaithfulExtractor`, nạp sidecar vào DBPage |
| `app/routers/documents.py` | sửa | thêm `view=goc\|dich` vào `get_page_content` |
| `tests/conftest.py` | sửa | fixture `sample_pdf` tạo bằng fitz |
| `tests/test_text_layer.py` | tạo mới | unit test text_layer |
| `tests/test_faithful_extractor.py` | tạo mới | unit test extractor (Docling tắt) |
| `tests/test_faithful_renderer.py` | tạo mới | unit test renderer |
| `tests/test_faithful_api.py` | tạo mới | test endpoint `view=goc\|dich` |

---

## Task 1: DB columns cho faithful artifacts

**Files:**
- Modify: `app/models_db.py:44-45`

- [ ] **Step 1: Thêm 2 cột vào DBPage**

Trong `app/models_db.py`, ngay sau dòng `model_json = Column(...)` (dòng 45), thêm:

```python
    svg_path            = Column(Text, nullable=True)   # faithful visual: "{doc}-{n}.svg" hoặc ".jpg"
    text_layer_json     = Column(Text, nullable=True)   # lớp text vô hình view Gốc
```

- [ ] **Step 2: Verify model import được**

Run: `cd apps/break_the_barriers/backend && .venv/bin/python -c "from backend.app.models_db import DBPage; print('svg_path' in DBPage.__table__.columns, 'text_layer_json' in DBPage.__table__.columns)"`
Expected: `True True`

- [ ] **Step 3: Ghi migration note cho Postgres**

Tạo file `apps/break_the_barriers/backend/migrations/2026-06-11-faithful-columns.sql` với nội dung:

```sql
-- Faithful SVG reader: thêm cột artifact cho bảng pages (prod Postgres).
-- SQLite test tự tạo từ model nên không cần chạy ở test.
ALTER TABLE pages ADD COLUMN IF NOT EXISTS svg_path TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS text_layer_json TEXT;
```

- [ ] **Step 4: Commit**

```bash
git add app/models_db.py migrations/2026-06-11-faithful-columns.sql
git commit -m "feat(db): add DBPage.svg_path + text_layer_json for faithful reader"
```

---

## Task 2: text_layer.py — trích text layer + reflow fallback

**Files:**
- Create: `app/services/text_layer.py`
- Create: `tests/test_text_layer.py`
- Modify: `tests/conftest.py` (thêm fixture `sample_pdf`)

- [ ] **Step 1: Thêm fixture sample_pdf vào conftest**

Trong `tests/conftest.py`, thêm fixture sau (đặt sau các import):

```python
import pytest

@pytest.fixture
def sample_pdf(tmp_path):
    """1-page PDF deterministic: 1 heading lớn + 1 đoạn body, tạo bằng fitz."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((50, 60), "Hello World Heading", fontsize=24)
    page.insert_text((50, 110), "This is a body paragraph for testing.", fontsize=11)
    out = tmp_path / "sample.pdf"
    doc.save(str(out))
    doc.close()
    return str(out)
```

- [ ] **Step 2: Viết test fail trước**

Tạo `tests/test_text_layer.py`:

```python
import fitz
from backend.app.services.text_layer import build_text_layer, reflow_blocks


def test_build_text_layer_returns_positioned_spans(sample_pdf):
    doc = fitz.open(sample_pdf)
    layer = build_text_layer(doc[0])
    doc.close()
    assert layer["page_w"] == 400 and layer["page_h"] == 300
    texts = " ".join(s["text"] for s in layer["spans"])
    assert "Hello World Heading" in texts
    for s in layer["spans"]:
        x, y, w, h = s["bbox"]
        assert w > 0 and h > 0 and x >= 0 and y >= 0


def test_reflow_blocks_tags_heading_by_font_size(sample_pdf):
    doc = fitz.open(sample_pdf)
    blocks = reflow_blocks(doc[0])
    doc.close()
    assert blocks, "reflow_blocks should return ordered text blocks"
    heading = next(b for b in blocks if "Heading" in b["text"])
    assert heading["role"] == "heading"
    body = next(b for b in blocks if "body paragraph" in b["text"])
    assert body["role"] == "body"
```

- [ ] **Step 3: Run test → fail**

Run: `.venv/bin/pytest tests/test_text_layer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.services.text_layer'`

- [ ] **Step 4: Implement text_layer.py**

Tạo `app/services/text_layer.py`:

```python
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
    body_size = sorted(it["size"] for it in items)[len(items) // 2]
    items.sort(key=lambda b: (round(b["bbox"][1]), b["bbox"][0]))  # top→bottom, left→right
    out: List[Dict[str, Any]] = []
    for it in items:
        role = "heading" if it["size"] >= body_size * 1.2 else "body"
        out.append({"text": it["text"], "bbox": it["bbox"], "role": role})
    return out
```

- [ ] **Step 5: Run test → pass**

Run: `.venv/bin/pytest tests/test_text_layer.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add app/services/text_layer.py tests/test_text_layer.py tests/conftest.py
git commit -m "feat(extract): text_layer build + reflow fallback from PyMuPDF"
```

---

## Task 3: faithful_extractor.py — sinh 3 sidecar/trang

**Files:**
- Create: `app/services/faithful_extractor.py`
- Create: `tests/test_faithful_extractor.py`

**Ghi chú:** Test ép Docling TẮT (monkeypatch `_docling_structure` → `None`) để nhanh và xác định; nhánh Docling thật chạy ở runtime.

- [ ] **Step 1: Viết test fail trước**

Tạo `tests/test_faithful_extractor.py`:

```python
import os
import json
from backend.app.services.faithful_extractor import FaithfulExtractor


def test_extract_pdf_writes_three_sidecars(sample_pdf, tmp_path, monkeypatch):
    # Ép Docling tắt → dùng reflow_blocks (nhanh, xác định)
    monkeypatch.setattr(FaithfulExtractor, "_docling_structure", staticmethod(lambda p: None))
    out_dir = str(tmp_path / "out")
    html_files = FaithfulExtractor.extract_pdf(sample_pdf, out_dir, "docX")

    assert len(html_files) == 1
    base = os.path.join(out_dir, "docX-1")

    # SVG faithful
    assert os.path.exists(base + ".svg")
    assert "<svg" in open(base + ".svg", encoding="utf-8").read()

    # text layer JSON có spans bbox
    tl = json.load(open(base + ".textlayer.json", encoding="utf-8"))
    assert tl["spans"] and len(tl["spans"][0]["bbox"]) == 4

    # reflow HTML có span id
    html = open(base + ".html", encoding="utf-8").read()
    assert 'id="s1"' in html
    assert "Hello World Heading" in html


def test_render_visual_falls_back_to_jpg_on_svg_error(sample_pdf, tmp_path, monkeypatch):
    import fitz
    doc = fitz.open(sample_pdf)
    page = doc[0]

    def boom():
        raise RuntimeError("svg fail")
    monkeypatch.setattr(page, "get_svg_image", boom)

    name = FaithfulExtractor._render_visual(page, str(tmp_path), "docY", 1)
    doc.close()
    assert name == "docY-1.jpg"
    assert os.path.exists(os.path.join(str(tmp_path), name))
```

- [ ] **Step 2: Run test → fail**

Run: `.venv/bin/pytest tests/test_faithful_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.services.faithful_extractor'`

- [ ] **Step 3: Implement faithful_extractor.py**

Tạo `app/services/faithful_extractor.py`:

```python
"""PDF → faithful SVG (Gốc) + text layer + reflow HTML (Dịch) per page.

Ghi cạnh nhau trong output_dir:
  {doc}-{n}.svg  (hoặc .jpg fallback) — visual nền trung thực
  {doc}-{n}.textlayer.json            — lớp text vô hình (copy/select)
  {doc}-{n}.html                      — reflow HTML có span id (nguồn dịch + nền Dịch)
Trả list path .html theo thứ tự trang (cùng interface extractor cũ)."""
import os
import json
import html as html_lib
import logging
from pathlib import Path
from collections import defaultdict
from typing import List, Optional
import fitz

from backend.app.services.text_layer import build_text_layer, reflow_blocks

logger = logging.getLogger(__name__)

_REFLOW_CSS = """
body{font-family:Arial,sans-serif;line-height:1.7;max-width:800px;margin:0 auto;padding:1.5rem;color:#333}
h1,h2,h3,h4,h5,h6{margin-top:1.4em;margin-bottom:.4em;line-height:1.3}
p{margin:.6em 0} ul,ol{padding-left:1.6em} li{margin:.3em 0}
table{border-collapse:collapse;width:100%;margin:1em 0} th,td{border:1px solid #ddd;padding:8px 12px;text-align:left}
th{background:#f2f2f2;font-weight:bold}
"""

_converter = None


class FaithfulExtractor:

    @classmethod
    def extract_pdf(cls, pdf_path: str, output_dir: str, doc_id: str) -> List[str]:
        os.makedirs(output_dir, exist_ok=True)
        doc = fitz.open(pdf_path)
        docling_pages = cls._docling_structure(pdf_path)  # {page_no: [(item,level)]} | None

        html_files: List[str] = []
        for i in range(len(doc)):
            page_no = i + 1
            page = doc[i]
            base = os.path.join(output_dir, f"{doc_id}-{page_no}")

            # 1) Faithful visual (SVG, raster JPG fallback)
            cls._render_visual(page, output_dir, doc_id, page_no)

            # 2) Text layer vô hình
            with open(base + ".textlayer.json", "w", encoding="utf-8") as f:
                json.dump(build_text_layer(page), f)

            # 3) Reflow HTML
            if docling_pages and docling_pages.get(page_no):
                body = cls._docling_items_to_body(docling_pages[page_no])
            else:
                body = cls._blocks_to_body(reflow_blocks(page))
            with open(base + ".html", "w", encoding="utf-8") as f:
                f.write(cls._wrap_doc(body))
            html_files.append(base + ".html")

        doc.close()
        return html_files

    # ── visual ──────────────────────────────────────────────────────────
    @staticmethod
    def _render_visual(page, output_dir: str, doc_id: str, page_no: int) -> str:
        try:
            svg = page.get_svg_image()
            name = f"{doc_id}-{page_no}.svg"
            with open(os.path.join(output_dir, name), "w", encoding="utf-8") as f:
                f.write(svg)
            return name
        except Exception as e:
            logger.warning(f"SVG render failed p{page_no}, raster fallback: {e}")
            name = f"{doc_id}-{page_no}.jpg"
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            pix.save(os.path.join(output_dir, name))
            return name

    # ── docling structure (CPU) ─────────────────────────────────────────
    @staticmethod
    def _docling_structure(pdf_path: str) -> Optional[dict]:
        global _converter
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice)
            if _converter is None:
                opts = PdfPipelineOptions()
                opts.do_ocr = False
                opts.generate_page_images = False
                opts.accelerator_options = AcceleratorOptions(
                    num_threads=4, device=AcceleratorDevice.CPU)
                _converter = DocumentConverter(
                    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
            result = _converter.convert(Path(pdf_path))
            pages = defaultdict(list)
            for item, level in result.document.iterate_items():
                if hasattr(item, "prov") and item.prov:
                    pages[item.prov[0].page_no].append((item, level))
            return pages
        except Exception as e:
            logger.warning(f"Docling structure failed, fallback to PyMuPDF reflow: {e}")
            return None

    # ── reflow HTML builders ────────────────────────────────────────────
    @staticmethod
    def _docling_items_to_body(items) -> str:
        parts: List[str] = []
        counter = [0]
        open_list = False

        def wrap(text: str) -> str:
            counter[0] += 1
            return f'<span id="s{counter[0]}">{html_lib.escape(text)}</span>'

        for item, level in items:
            text = (getattr(item, "text", "") or "").strip()
            label = str(getattr(item, "label", "text"))
            if label == "list_item":
                if not open_list:
                    parts.append("<ul>"); open_list = True
                if text:
                    parts.append(f"<li>{wrap(text)}</li>")
                continue
            if open_list:
                parts.append("</ul>"); open_list = False
            if not text:
                continue
            if label == "section_header":
                h = min(max(level + 1, 2), 6)
                parts.append(f"<h{h}>{wrap(text)}</h{h}>")
            elif label == "table":
                parts.append(FaithfulExtractor._table_to_html(text, wrap))
            else:
                parts.append(f"<p>{wrap(text)}</p>")
        if open_list:
            parts.append("</ul>")
        return "\n".join(parts)

    @staticmethod
    def _blocks_to_body(blocks) -> str:
        parts: List[str] = []
        for i, b in enumerate(blocks, start=1):
            span = f'<span id="s{i}">{html_lib.escape(b["text"])}</span>'
            if b.get("role") == "heading":
                parts.append(f"<h2>{span}</h2>")
            else:
                parts.append(f"<p>{span}</p>")
        return "\n".join(parts)

    @staticmethod
    def _table_to_html(text: str, wrap) -> str:
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        if not lines or "\t" not in lines[0]:
            return f"<p>{wrap(text)}</p>"
        rows = [ln.split("\t") for ln in lines]
        head = "".join(f"<th>{wrap(c.strip())}</th>" for c in rows[0])
        body = "".join(
            "<tr>" + "".join(f"<td>{wrap(c.strip())}</td>" for c in r) + "</tr>"
            for r in rows[1:])
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    @staticmethod
    def _wrap_doc(body: str) -> str:
        return (
            "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"<style>\n{_REFLOW_CSS}\n</style>\n</head>\n<body>\n"
            + body + "\n</body>\n</html>")
```

- [ ] **Step 4: Run test → pass**

Run: `.venv/bin/pytest tests/test_faithful_extractor.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/faithful_extractor.py tests/test_faithful_extractor.py
git commit -m "feat(extract): FaithfulExtractor — SVG + text layer + reflow per page"
```

---

## Task 4: faithful_renderer.py — ráp HTML view Gốc

**Files:**
- Create: `app/services/faithful_renderer.py`
- Create: `tests/test_faithful_renderer.py`

- [ ] **Step 1: Viết test fail trước**

Tạo `tests/test_faithful_renderer.py`:

```python
from backend.app.services.faithful_renderer import render_faithful_page

LAYER = {"page_w": 400, "page_h": 300,
         "spans": [{"bbox": [50, 60, 120, 24], "text": "Hello <World>"}]}


def test_render_svg_inlines_and_overlays_transparent_text():
    html = render_faithful_page("<svg id='x'></svg>", "svg", LAYER, 400, 300)
    assert "<svg id='x'></svg>" in html          # SVG inline nguyên văn
    assert 'class="ff-tl"' in html               # lớp text vô hình
    assert "left:50.00px" in html and "top:60.00px" in html
    assert "Hello &lt;World&gt;" in html         # text được escape
    assert "width:400" in html and "height:300"  # container kích thước trang


def test_render_image_kind_uses_img_tag():
    html = render_faithful_page("docY-1.jpg", "image", LAYER, 400, 300,
                                asset_base="http://api/x/assets")
    assert '<img src="http://api/x/assets/docY-1.jpg"' in html
    assert "<svg" not in html
```

- [ ] **Step 2: Run test → fail**

Run: `.venv/bin/pytest tests/test_faithful_renderer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.services.faithful_renderer'`

- [ ] **Step 3: Implement faithful_renderer.py**

Tạo `app/services/faithful_renderer.py`:

```python
"""Ráp HTML view Gốc: visual nền trung thực (SVG inline hoặc <img>) + lớp <span>
trong suốt định vị theo bbox để bôi đen/copy. Container có style width/height (px)
để script page_size của documents.py đọc được kích thước trang."""
import html as html_lib
from typing import Dict, Any

_FAITHFUL_CSS = """
*{box-sizing:border-box} body{margin:0;background:#fff}
.ff-page{position:relative;margin:0 auto}
.ff-page > svg,.ff-page > img{position:absolute;inset:0;width:100%;height:100%;display:block}
.ff-tl{position:absolute;color:transparent;white-space:pre;transform-origin:0 0;user-select:text}
"""


def render_faithful_page(visual: str, visual_kind: str, text_layer: Dict[str, Any],
                         page_w: float, page_h: float, asset_base: str = "") -> str:
    if visual_kind == "svg":
        base = visual
    else:
        src = f"{asset_base}/{visual}" if asset_base else visual
        base = f'<img src="{html_lib.escape(src, quote=True)}" alt=""/>'

    spans = []
    for s in text_layer.get("spans", []):
        x, y, w, h = s["bbox"]
        spans.append(
            f'<span class="ff-tl" style="left:{x:.2f}px;top:{y:.2f}px">'
            f'{html_lib.escape(s["text"])}</span>')

    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"<style>\n{_FAITHFUL_CSS}\n</style>\n</head>\n<body>\n"
        f'<div class="ff-page" style="width:{page_w:.0f}px;height:{page_h:.0f}px">\n'
        f"{base}\n" + "\n".join(spans) +
        "\n</div>\n</body>\n</html>")
```

- [ ] **Step 4: Run test → pass**

Run: `.venv/bin/pytest tests/test_faithful_renderer.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/services/faithful_renderer.py tests/test_faithful_renderer.py
git commit -m "feat(render): render_faithful_page — SVG/img + transparent text layer"
```

---

## Task 5: Wiring extraction.py — dùng FaithfulExtractor + nạp sidecar

**Files:**
- Modify: `app/routers/extraction.py:14` (import), `:66-86` (PDF branch), `:90-123` (loop)
- Create: `tests/test_faithful_extraction_wiring.py`

- [ ] **Step 1: Viết test fail trước**

Tạo `tests/test_faithful_extraction_wiring.py`:

```python
import os
import shutil
from backend.app.services.faithful_extractor import FaithfulExtractor
from backend.app.routers.extraction import _perform_extraction
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.core import DATA_DIR


def test_extraction_populates_faithful_columns(db_session, sample_pdf, monkeypatch):
    monkeypatch.setattr(FaithfulExtractor, "_docling_structure", staticmethod(lambda p: None))
    doc_id = "wiretest"
    # đặt PDF vào nơi extraction tìm: data/raw_pdf/<doc_id>.pdf
    raw_dir = os.path.join(DATA_DIR, "raw_pdf")
    os.makedirs(raw_dir, exist_ok=True)
    shutil.copy(sample_pdf, os.path.join(raw_dir, f"{doc_id}.pdf"))

    db_session.add(DBDocument(id=doc_id, filename="sample.pdf", total_pages=1, status="raw"))
    db_session.commit()

    _perform_extraction(doc_id, db_session)

    page = db_session.query(DBPage).filter_by(document_id=doc_id, page_num=1).first()
    assert page is not None
    assert page.svg_path == f"{doc_id}-1.svg"
    assert page.text_layer_json and "spans" in page.text_layer_json
    assert 'id="s1"' in page.original_html
    trans = db_session.query(DBTranslation).filter_by(document_id=doc_id).all()
    assert any("Heading" in t.original_text for t in trans)

    # cleanup
    os.remove(os.path.join(raw_dir, f"{doc_id}.pdf"))
    shutil.rmtree(os.path.join(DATA_DIR, "extracted_html", doc_id), ignore_errors=True)
```

**Lưu ý:** kiểm tra `tests/conftest.py` đã có fixture session tên `db_session`. Nếu tên khác (vd `db`), đổi cho khớp.

- [ ] **Step 2: Run test → fail**

Run: `.venv/bin/pytest tests/test_faithful_extraction_wiring.py -v`
Expected: FAIL — `AssertionError` ở `page.svg_path` (vẫn None vì extraction chưa dùng FaithfulExtractor)

- [ ] **Step 3: Sửa import trong extraction.py**

Tại `app/routers/extraction.py:14`, đổi:

```python
from backend.app.services.extractor import Extractor, DoclingExtractor
```
thành:
```python
from backend.app.services.extractor import Extractor, DoclingExtractor
from backend.app.services.faithful_extractor import FaithfulExtractor
```

- [ ] **Step 4: Đổi PDF branch dùng FaithfulExtractor**

Tại `app/routers/extraction.py`, trong nhánh PDF (khoảng dòng 67-73), đổi:

```python
            try:
                html_files = DoclingExtractor.extract_pdf_to_html(pdf_path, extracted_dir, doc_id)
                use_docling = True
                logger.info(f"DoclingExtractor produced {len(html_files)} pages for {doc_id}")
            except Exception as docling_err:
                logger.warning(f"DoclingExtractor failed ({docling_err}), falling back to pdftohtml")
```
thành:
```python
            try:
                html_files = FaithfulExtractor.extract_pdf(pdf_path, extracted_dir, doc_id)
                use_docling = True
                logger.info(f"FaithfulExtractor produced {len(html_files)} pages for {doc_id}")
            except Exception as faithful_err:
                logger.warning(f"FaithfulExtractor failed ({faithful_err}), falling back to pdftohtml")
```

- [ ] **Step 5: Nạp sidecar mới vào DBPage**

Tại `app/routers/extraction.py`, trong vòng lặp per-page, thay khối đọc sidecar + `db.add(DBPage(...))` (khoảng dòng 107-121) bằng:

```python
            layout_json = None
            layout_path = file_path[:-5] + ".layout.json"
            if os.path.exists(layout_path):
                with open(layout_path, "r", encoding="utf-8") as lf:
                    layout_json = lf.read()

            model_json = None
            model_path = file_path[:-5] + ".model.json"
            if os.path.exists(model_path):
                with open(model_path, "r", encoding="utf-8") as mf:
                    model_json = mf.read()

            # Faithful sidecars (SVG reader)
            text_layer_json = None
            tl_path = file_path[:-5] + ".textlayer.json"
            if os.path.exists(tl_path):
                with open(tl_path, "r", encoding="utf-8") as tf:
                    text_layer_json = tf.read()
            svg_path = None
            for _ext in (".svg", ".jpg"):
                _cand = file_path[:-5] + _ext
                if os.path.exists(_cand):
                    svg_path = os.path.basename(_cand)
                    break

            spans = Extractor.extract_spans(final_html)
            db.add(DBPage(document_id=doc_id, page_num=page_num, original_html=final_html,
                          status="raw", layout_json=layout_json, model_json=model_json,
                          svg_path=svg_path, text_layer_json=text_layer_json))
            for s in spans:
                db.add(DBTranslation(document_id=doc_id, page_num=page_num, span_id=s["id"], original_text=s["text"]))
```

- [ ] **Step 6: Run test → pass**

Run: `.venv/bin/pytest tests/test_faithful_extraction_wiring.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add app/routers/extraction.py tests/test_faithful_extraction_wiring.py
git commit -m "feat(extract): wire FaithfulExtractor + persist svg_path/text_layer_json"
```

---

## Task 6: Endpoint view=goc|dich trong documents.py

**Files:**
- Modify: `app/routers/documents.py:230-237` (signature), `:248-249` (branch sớm)
- Create: `tests/test_faithful_api.py`

- [ ] **Step 1: Viết test fail trước**

Tạo `tests/test_faithful_api.py`:

```python
import os
import json
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.core import DATA_DIR


def _seed(db, client, doc_id="apidoc"):
    out_dir = os.path.join(DATA_DIR, "extracted_html", doc_id)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{doc_id}-1.svg"), "w", encoding="utf-8") as f:
        f.write("<svg id='real'></svg>")
    tl = {"page_w": 400, "page_h": 300, "spans": [{"bbox": [10, 20, 80, 14], "text": "Origin"}]}
    db.add(DBDocument(id=doc_id, filename="d.pdf", total_pages=1, status="extracted"))
    db.add(DBPage(document_id=doc_id, page_num=1, status="extracted",
                  original_html='<p><span id="s1">Origin text</span></p>',
                  svg_path=f"{doc_id}-1.svg", text_layer_json=json.dumps(tl)))
    db.add(DBTranslation(document_id=doc_id, page_num=1, span_id="s1",
                         original_text="Origin text", translated_text="Bản dịch"))
    db.commit()
    return doc_id


def test_view_goc_returns_svg_with_text_layer(client, db_session):
    doc_id = _seed(db_session, client, "apidoc_goc")
    r = client.get(f"/api/docs/{doc_id}/pages/1?view=goc")
    data = r.json()
    assert "<svg id='real'></svg>" in data["html"]
    assert 'class="ff-tl"' in data["html"]
    os.remove(os.path.join(DATA_DIR, "extracted_html", doc_id, f"{doc_id}-1.svg"))


def test_view_dich_injects_translation(client, db_session):
    doc_id = _seed(db_session, client, "apidoc_dich")
    r = client.get(f"/api/docs/{doc_id}/pages/1?view=dich")
    data = r.json()
    assert "Bản dịch" in data["html"]


def test_view_goc_raw_returns_html_response(client, db_session):
    doc_id = _seed(db_session, client, "apidoc_raw")
    r = client.get(f"/api/docs/{doc_id}/pages/1?view=goc&raw=true")
    assert r.headers["content-type"].startswith("text/html")
    assert "ff-page" in r.text and "page_size" in r.text
    os.remove(os.path.join(DATA_DIR, "extracted_html", doc_id, f"{doc_id}-1.svg"))
```

**Lưu ý:** kiểm tra `conftest.py` có fixture `client` (TestClient) và `db_session`. Đổi tên cho khớp nếu cần.

- [ ] **Step 2: Run test → fail**

Run: `.venv/bin/pytest tests/test_faithful_api.py -v`
Expected: FAIL — `view=goc` chưa xử lý, trả nhành vi cũ (không có `<svg id='real'>`)

- [ ] **Step 3: Thêm param `view` vào signature**

Tại `app/routers/documents.py:234`, sau dòng `lang: str = Query(...)`, thêm:

```python
    view: Optional[str] = Query(None, pattern="^(goc|dich)$"),
```

Đảm bảo đầu file có `from typing import Optional` (thêm nếu thiếu).

- [ ] **Step 4: Thêm nhánh xử lý view sớm**

Tại `app/routers/documents.py`, NGAY SAU khi load `page` (sau dòng 247 `raise HTTPException(... "Page not found")`), thêm khối:

```python
    if view is not None:
        from backend.app.models_db import DBTranslation as _DBT
        if view == "goc":
            import json as _json
            import os as _os
            from backend.app.core import DATA_DIR as _DATA
            from backend.app.services.faithful_renderer import render_faithful_page
            tl = _json.loads(page.text_layer_json) if page.text_layer_json else {"spans": []}
            pw = tl.get("page_w") or 900.0
            ph = tl.get("page_h") or 1260.0
            visual = page.svg_path or ""
            asset_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
            if visual.endswith(".svg"):
                svg_file = _os.path.join(_DATA, "extracted_html", doc_id, visual)
                svg = open(svg_file, "r", encoding="utf-8").read() if _os.path.exists(svg_file) else "<svg></svg>"
                html = render_faithful_page(svg, "svg", tl, pw, ph)
            else:
                html = render_faithful_page(visual, "image", tl, pw, ph, asset_base)
        else:  # view == "dich"
            from backend.app.services.compiler import Compiler as _Compiler
            rows = db.query(_DBT).filter(_DBT.document_id == doc_id,
                                         _DBT.page_num == page_num).all()
            trans_dict = {t.span_id: (t.translated_text or t.original_text or "") for t in rows}
            html = _Compiler.inject_translation(page.original_html or "", trans_dict)

        if raw:
            return HTMLResponse(content=_inject_page_size(html, page_num, pw if view == "goc" else 900, ph if view == "goc" else 1260))
        return {"doc_id": doc_id, "page_num": page_num, "lang": lang, "view": view,
                "html": html, "page_class": "text", "cover": "none",
                "policy_override": None, "has_clean_image": False}
```

- [ ] **Step 5: Tách helper `_inject_page_size`**

Để tránh trùng lặp script postMessage, thêm hàm module-level trong `app/routers/documents.py` (đặt trước `get_page_content`):

```python
def _inject_page_size(html: str, page_num: int, w, h) -> str:
    script = (
        "<script>window.addEventListener('load',()=>{"
        "window.parent.postMessage({type:'page_size',width:%d,height:%d,page_num:%d},'*');"
        "});</script>" % (int(w), int(h), page_num))
    low = (html or "").lower()
    if "</head>" in low:
        return html.replace("</head>", script + "</head>", 1)
    if "</body>" in low:
        return html.replace("</body>", script + "</body>", 1)
    return (html or "") + script
```

(Nhánh cũ `raw` ở cuối hàm giữ nguyên — không bắt buộc refactor sang helper trong đợt này.)

- [ ] **Step 6: Run test → pass**

Run: `.venv/bin/pytest tests/test_faithful_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add app/routers/documents.py tests/test_faithful_api.py
git commit -m "feat(api): view=goc|dich on get_page_content (faithful SVG / reflow)"
```

---

## Task 7: Verify toàn bộ + smoke test thật

**Files:** không sửa code — chỉ verify.

- [ ] **Step 1: Chạy full suite**

Run: `cd apps/break_the_barriers/backend && .venv/bin/pytest tests/ -v`
Expected: tất cả PASS (kể cả test cũ — backward compat: `view=None` giữ nguyên hành vi).

- [ ] **Step 2: Smoke test extraction thật trên PDF có sẵn (Docling BẬT)**

Run:
```bash
cd apps/break_the_barriers/backend
.venv/bin/python -c "
from backend.app.services.faithful_extractor import FaithfulExtractor
import tempfile, os, json
out = tempfile.mkdtemp()
files = FaithfulExtractor.extract_pdf('data/raw_pdf/2024-wttc-introduction-to-ai.pdf', out, 'smoke')
print('pages:', len(files))
b = os.path.join(out, 'smoke-3')
print('svg KB:', round(os.path.getsize(b+'.svg')/1024))
tl = json.load(open(b+'.textlayer.json')); print('spans:', len(tl['spans']))
print('reflow has span:', 'id=\"s1\"' in open(b+'.html').read())
"
```
Expected: in ra `pages: 44`, `svg KB:` > 0, `spans:` > 0, `reflow has span: True`. (Docling chạy thật ~1.3s/trang — chờ 1-2 phút.)

- [ ] **Step 3: Verify SVG mở được trên trình duyệt (fidelity mắt thường)**

Run: `open $(ls -t /tmp/*/smoke-3.svg 2>/dev/null | head -1)` — HOẶC copy 1 file SVG ra desktop và mở. Mắt thường so với trang 3 PDF gốc: phải y hệt.

- [ ] **Step 4: Báo cáo kết quả**

Ghi lại: số test pass, kích thước SVG mẫu, số span text layer, và xác nhận fidelity mắt thường. Nếu mọi thứ xanh → pipeline mới sẵn sàng; bước kế tiếp (đợt sau) là frontend toggle Gốc/Dịch + task cleanup service cũ (§8 spec).

---

## Self-Review Notes (đã kiểm)

- **Spec coverage:** §4 components → Task 2-4; §5.2 DB → Task 1; §5.3 endpoint → Task 6; §5.4 render Gốc → Task 4; §6 fallback → Task 3 (SVG→JPG) + Task 2/3 (Docling→blocks); §7 tests → mỗi task có test. §8 cleanup ngoài phạm vi (đã ghi). ✔
- **Type consistency:** `render_faithful_page(visual, visual_kind, text_layer, page_w, page_h, asset_base="")` đồng nhất giữa Task 4 và Task 6. `FaithfulExtractor.extract_pdf` / `_render_visual` / `_docling_structure` đồng nhất giữa Task 3 và 5. text_layer shape `{"page_w","page_h","spans":[{"bbox","text"}]}` đồng nhất Task 2/3/4/6. ✔
- **Fixture names:** Task 5/6 ghi chú phải khớp tên fixture thật trong `conftest.py` (`db_session`/`client`) — verify ở Step 1 mỗi task. ✔
- **Backward compat:** `view=None` → nhánh cũ nguyên vẹn; cột mới nullable; sidecar cũ vẫn đọc. ✔
