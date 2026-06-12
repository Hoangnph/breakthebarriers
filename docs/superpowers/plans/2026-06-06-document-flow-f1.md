# Document Flow Model + Renderer (F1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gộp các PageModel của một tài liệu thành một danh sách flow elements rồi render thành HTML semantic cuộn dọc (text flow + khối-ảnh cho trang thiết kế), phục vụ qua endpoint `/flow`.

**Architecture:** `flow_model.build_document_flow` định tuyến mỗi trang bằng `effective_policy` (text→element, design→image_block), gắn cấp heading theo hạng font; `flow_renderer.render_flow_html` xuất HTML semantic với `data-span`; endpoint `/flow` ráp từ model_json + translations.

**Tech Stack:** Python 3, FastAPI, pytest. Backend `apps/break_the_barriers/backend`, test `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-06-document-flow-f1-design.md`

## File Structure

- `app/services/flow_model.py` — **mới**; `FlowElement` + `build_document_flow`.
- `app/services/flow_renderer.py` — **mới**; `render_flow_html`.
- `app/routers/documents.py` — endpoint `GET /api/docs/{id}/flow`.
- Tests: `tests/test_flow_model.py`, `tests/test_flow_renderer.py` (mới); bổ sung `tests/test_preview_pagemodel.py`.

**Lệnh:** test từ `apps/break_the_barriers/backend` (`.venv/bin/pytest`); git từ repo root. Nhánh `feat/document-flow` (đã checkout — KHÔNG tạo nhánh). Import `backend.app...`.

Ngữ cảnh tái dùng:
- `PageModel` (page_class, cover, background dict, blocks[Block{span_id,role,bbox,font}], figures[Figure{img,clean_img,bbox}]).
- `effective_policy(page_class, cover, override)` trong `app/services/background_policy.py`.
- Endpoint mẫu: `image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"`; pages = `db.query(DBPage).filter(DBPage.document_id==doc_id).order_by(DBPage.page_num).all()`; translations = `db.query(DBTranslation).filter(DBTranslation.document_id==doc_id).all()`.

---

### Task 1: `flow_model.py` — FlowElement + build_document_flow

**Files:**
- Create: `app/services/flow_model.py`
- Test: `tests/test_flow_model.py`

- [ ] **Step 1: Viết test thất bại** — tạo `tests/test_flow_model.py`:

```python
from backend.app.services.page_model import PageModel, Block, Figure, FontSpec
from backend.app.services.flow_model import build_document_flow, FlowElement


def _txt(span, role, top, size):
    return Block(span_id=span, role=role, bbox=[72, top, 300, 20], text="",
                 font=FontSpec(size, 700 if role == "heading" else 400, False, "#000", "left", "sans"))


def test_text_page_flows_blocks_in_top_order():
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[_txt("h", "heading", 40, 28), _txt("p1", "body", 80, 11),
                             _txt("c", "caption", 200, 9)],
                     figures=[Figure(bbox=[72, 120, 100, 50], img="f.png")],
                     page_class="text", cover="none")
    flow = build_document_flow([page])
    kinds = [(e.kind, e.span_id or e.src) for e in flow]
    assert kinds == [("heading", "h"), ("paragraph", "p1"),
                     ("figure", "f.png"), ("caption", "c")]   # sorted by top
    assert flow[0].level == 1


def test_clean_photo_page_emits_image_block():
    page = PageModel(page_w=595.0, page_h=842.0, kind="mixed",
                     background={"color": "#000", "image": "p1.png", "clean_image": "p1.clean.png"},
                     blocks=[_txt("t", "heading", 500, 36)], figures=[],
                     page_class="regenerable", cover="front")   # -> clean-photo
    flow = build_document_flow([page])
    assert flow[0].kind == "image_block"
    assert flow[0].src == "p1.clean.png"          # cleaned variant preferred
    assert any(e.kind == "heading" and e.span_id == "t" for e in flow)


def test_base_color_page_has_no_image_block():
    page = PageModel(page_w=595.0, page_h=842.0, kind="mixed",
                     background={"color": "#000", "image": "p2.png"},
                     blocks=[_txt("b", "body", 40, 11)], figures=[],
                     page_class="regenerable", cover="none")   # -> base-color
    flow = build_document_flow([page])
    assert all(e.kind != "image_block" for e in flow)


def test_heading_levels_ranked_by_font_size():
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[_txt("big", "heading", 40, 32), _txt("med", "heading", 80, 20),
                             _txt("body", "body", 120, 11)],
                     figures=[], page_class="text", cover="none")
    flow = {e.span_id: e for e in build_document_flow([page]) if e.span_id}
    assert flow["big"].level == 1 and flow["med"].level == 2
    assert flow["body"].kind == "paragraph"
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_flow_model.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Cài đặt.** Tạo `app/services/flow_model.py`:

```python
"""Build a single flowing-document model (ordered FlowElements) from a list of
per-page PageModels. Text pages flow their blocks; design pages (clean-photo /
keep-raster) contribute a full-width image_block. Pure: structure only — text is
filled at render time from translations."""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from typing import List, Optional

from backend.app.services.page_model import PageModel
from backend.app.services.background_policy import effective_policy


@dataclass
class FlowElement:
    kind: str                      # heading|paragraph|caption|list|figure|image_block
    span_id: Optional[str] = None
    level: int = 0                 # heading: 1..3
    src: Optional[str] = None      # figure/image_block filename


def _body_size(pages: List[PageModel]) -> float:
    sizes = [b.font.size for p in pages for b in p.blocks
             if b.role == "body" and b.font and b.font.size]
    if not sizes:
        return 11.0
    return Counter(sizes).most_common(1)[0][0]


def _is_heading(b, body_size: float) -> bool:
    fs = b.font.size if b.font and b.font.size else 0
    return b.role == "heading" or (fs and fs >= body_size * 1.3)


def build_document_flow(pages: List[PageModel]) -> List[FlowElement]:
    body_size = _body_size(pages)
    heading_sizes = sorted(
        {(b.font.size if b.font and b.font.size else 0)
         for p in pages for b in p.blocks if _is_heading(b, body_size)},
        reverse=True)

    def level(b) -> int:
        fs = b.font.size if b.font and b.font.size else 0
        try:
            return min(heading_sizes.index(fs) + 1, 3)
        except ValueError:
            return 3

    flow: List[FlowElement] = []
    for p in pages:
        policy = effective_policy(p.page_class, p.cover,
                                  (p.background or {}).get("policy_override"))
        if policy in ("clean-photo", "keep-raster"):
            bgd = p.background or {}
            src = (bgd.get("clean_image") if policy == "clean-photo" else None) or bgd.get("image")
            if src:
                flow.append(FlowElement(kind="image_block", src=src))
        # Interleave text blocks + figures by vertical position (reading order).
        items = [("blk", b, b.bbox[1]) for b in p.blocks] + \
                [("fig", f, f.bbox[1]) for f in p.figures]
        items.sort(key=lambda it: it[2])
        for tag, obj, _top in items:
            if tag == "fig":
                flow.append(FlowElement(kind="figure", src=(obj.clean_img or obj.img)))
            elif _is_heading(obj, body_size):
                flow.append(FlowElement(kind="heading", span_id=obj.span_id, level=level(obj)))
            elif obj.role == "caption":
                flow.append(FlowElement(kind="caption", span_id=obj.span_id))
            elif obj.role == "list":
                flow.append(FlowElement(kind="list", span_id=obj.span_id))
            else:
                flow.append(FlowElement(kind="paragraph", span_id=obj.span_id))
    return flow
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_flow_model.py -v` → 4 passed.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/flow_model.py \
        apps/break_the_barriers/backend/tests/test_flow_model.py
git commit -m "feat(F1): build_document_flow (FlowElement model from PageModels)"
```

---

### Task 2: `flow_renderer.py` — render_flow_html

**Files:**
- Create: `app/services/flow_renderer.py`
- Test: `tests/test_flow_renderer.py`

- [ ] **Step 1: Viết test thất bại** — tạo `tests/test_flow_renderer.py`:

```python
from backend.app.services.flow_model import FlowElement
from backend.app.services.flow_renderer import render_flow_html


def test_renders_semantic_tags_with_translations():
    flow = [FlowElement(kind="heading", span_id="h", level=1),
            FlowElement(kind="paragraph", span_id="p"),
            FlowElement(kind="figure", src="f.png"),
            FlowElement(kind="image_block", src="cover.clean.png")]
    html = render_flow_html(flow, {"h": "Tiêu đề", "p": "Đoạn văn"},
                            image_url_base="http://api/assets")
    assert "<h1" in html and "Tiêu đề" in html
    assert "<p" in html and "Đoạn văn" in html
    assert 'data-span="h"' in html and 'data-span="p"' in html
    assert 'class="fl-fig" src="http://api/assets/f.png"' in html
    assert 'class="fl-page" src="http://api/assets/cover.clean.png"' in html


def test_skips_text_without_translation():
    flow = [FlowElement(kind="paragraph", span_id="x")]
    html = render_flow_html(flow, {}, image_url_base="http://api/a")
    assert 'data-span="x"' not in html


def test_escapes_text():
    flow = [FlowElement(kind="paragraph", span_id="p")]
    html = render_flow_html(flow, {"p": "a < b & c"}, image_url_base="http://api/a")
    assert "a &lt; b &amp; c" in html
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_flow_renderer.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Cài đặt.** Tạo `app/services/flow_renderer.py`:

```python
"""Render a list of FlowElements as a single scrolling semantic HTML document."""
from __future__ import annotations
import html as html_lib
from typing import List

from backend.app.services.flow_model import FlowElement

_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Be+Vietnam+Pro:wght@400;700&display=swap" rel="stylesheet">'
)
_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #f4f4f5; font-family: 'Be Vietnam Pro', system-ui, sans-serif; }
.fl-doc { max-width: 720px; margin: 0 auto; padding: 48px 24px 120px;
          background: #fff; color: #1a1a1a; line-height: 1.7; }
.fl-doc h1 { font-size: 2rem; margin: 1.6em 0 .5em; line-height: 1.25; }
.fl-doc h2 { font-size: 1.5rem; margin: 1.4em 0 .5em; }
.fl-doc h3 { font-size: 1.2rem; margin: 1.2em 0 .5em; }
.fl-doc p { margin: 0 0 1em; }
.fl-doc p.cap { font-size: .9rem; color: #666; }
.fl-doc figure { margin: 1.5em 0; }
.fl-fig { max-width: 100%; height: auto; display: block; }
.fl-page { width: 100%; height: auto; display: block; margin: 1.5em 0;
           border-radius: 4px; }
"""


def render_flow_html(flow: List[FlowElement], translations: dict,
                     image_url_base: str) -> str:
    parts: List[str] = []
    for el in flow:
        if el.kind == "image_block" and el.src:
            src = html_lib.escape(f"{image_url_base}/{el.src}", quote=True)
            parts.append(f'<img class="fl-page" src="{src}" alt="page"/>')
            continue
        if el.kind == "figure" and el.src:
            src = html_lib.escape(f"{image_url_base}/{el.src}", quote=True)
            parts.append(f'<figure><img class="fl-fig" src="{src}" alt="figure"/></figure>')
            continue
        text = (translations or {}).get(el.span_id)
        if not text:
            continue
        span = html_lib.escape(el.span_id or "", quote=True)
        body = html_lib.escape(text)
        if el.kind == "heading":
            lvl = el.level if el.level in (1, 2, 3) else 3
            parts.append(f'<h{lvl} data-span="{span}">{body}</h{lvl}>')
        elif el.kind == "caption":
            parts.append(f'<p class="cap" data-span="{span}">{body}</p>')
        elif el.kind == "list":
            parts.append(f'<p class="li" data-span="{span}">• {body}</p>')
        else:
            parts.append(f'<p data-span="{span}">{body}</p>')
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'{_FONTS}<style>{_CSS}</style></head><body>'
        f'<article class="fl-doc">{"".join(parts)}</article></body></html>'
    )
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_flow_renderer.py -v` → 3 passed.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/flow_renderer.py \
        apps/break_the_barriers/backend/tests/test_flow_renderer.py
git commit -m "feat(F1): render_flow_html (semantic scrolling document)"
```

---

### Task 3: Endpoint `GET /api/docs/{id}/flow`

**Files:**
- Modify: `app/routers/documents.py`
- Test: `tests/test_preview_pagemodel.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_preview_pagemodel.py`:

```python
def test_flow_endpoint_returns_document_html(client, db_session):
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="fl_doc", filename="f.pdf", total_pages=2, status="translated"))
    m1 = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
          "background": {"color": "#fff", "image": None},
          "blocks": [{"span_id": "h", "role": "heading", "bbox": [72, 40, 300, 28], "text": "",
                      "font": {"size": 28, "weight": 700, "italic": False, "color": "#000",
                               "align": "left", "family_class": "sans"}}],
          "figures": [], "page_class": "text", "cover": "none"}
    m2 = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
          "background": {"color": "#fff", "image": None},
          "blocks": [{"span_id": "p", "role": "body", "bbox": [72, 40, 300, 60], "text": "",
                      "font": {"size": 11, "weight": 400, "italic": False, "color": "#000",
                               "align": "left", "family_class": "sans"}}],
          "figures": [], "page_class": "text", "cover": "none"}
    db_session.add(DBPage(document_id="fl_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(m1)))
    db_session.add(DBPage(document_id="fl_doc", page_num=2, original_html="<p/>",
                          status="translated", model_json=json.dumps(m2)))
    db_session.add(DBTranslation(document_id="fl_doc", page_num=1, span_id="h",
                                 original_text="TITLE", translated_text="TIÊU ĐỀ"))
    db_session.add(DBTranslation(document_id="fl_doc", page_num=2, span_id="p",
                                 original_text="body", translated_text="đoạn văn dịch"))
    db_session.commit()
    r = client.get("/api/docs/fl_doc/flow?lang=vi")
    assert r.status_code == 200
    assert "TIÊU ĐỀ" in r.text and "<h1" in r.text
    assert "đoạn văn dịch" in r.text and "<p" in r.text
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_preview_pagemodel.py -k flow_endpoint -v` → 404.

- [ ] **Step 3: Cài đặt.** Trong `app/routers/documents.py`, thêm endpoint (sau `get_page_content` hoặc cuối file). Dùng các import sẵn có (`DBPage`, `DBDocument`, `Request`, `Query`, `Depends`, `get_db`, `HTMLResponse`):

```python
@router.get("/api/docs/{doc_id}/flow")
def get_document_flow(doc_id: str, request: Request,
                      lang: str = Query("vi", pattern="^(en|vi)$"),
                      db: Session = Depends(get_db)):
    from backend.app.services.page_model import PageModel
    from backend.app.services.flow_model import build_document_flow
    from backend.app.services.flow_renderer import render_flow_html
    from backend.app.models_db import DBTranslation

    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    page_rows = (db.query(DBPage).filter(DBPage.document_id == doc_id)
                 .order_by(DBPage.page_num).all())
    pages = []
    for pr in page_rows:
        if pr.model_json:
            try:
                pages.append(PageModel.from_json(pr.model_json))
            except Exception:
                pass
    rows = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id).all()
    if lang == "en":
        trans = {t.span_id: (t.original_text or "") for t in rows}
    else:
        trans = {t.span_id: (t.translated_text or "") for t in rows}
    image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
    flow = build_document_flow(pages)
    html = render_flow_html(flow, trans, image_base)
    return HTMLResponse(content=html)
```
Đảm bảo `HTMLResponse`, `Request`, `Session` đã import ở đầu file (get_page_content đã dùng chúng — nếu thiếu thì thêm).

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_preview_pagemodel.py -v` → tất cả pass (gồm test flow mới).

- [ ] **Step 5: Full suite** — `.venv/bin/pytest tests/ -q --ignore=tests/test_extractor_box.py --ignore=tests/test_extractor_overhaul.py --ignore=tests/test_extractor_pagemodel.py` → all pass. Báo số đếm.

- [ ] **Step 6: Commit**
```bash
git add apps/break_the_barriers/backend/app/routers/documents.py \
        apps/break_the_barriers/backend/tests/test_preview_pagemodel.py
git commit -m "feat(F1): GET /api/docs/{id}/flow endpoint (whole-document flow HTML)"
```

---

### Task 4: Verify thật tài liệu flow (manual — controller)

**Files:** không.

- [ ] **Step 1:** Backend `--reload` đã có code mới. Chrome headless screenshot `GET /api/docs/2024-wttc-introduction-to-ai/flow?lang=vi` (chụp phần đầu — bìa image_block + tiêu đề + vài đoạn + mục lục).
- [ ] **Step 2:** Đánh giá dưới mắt độc giả: chữ dịch chảy tự nhiên, không clip/đè; bìa hiện là khối-ảnh; heading/đoạn rõ ràng. So với chế độ trang. Gửi ảnh + báo cáo (nêu rủi ro thứ-tự-đọc/đa-cột nếu thấy).

---

## Self-Review

**Spec coverage:**
- A `FlowElement` + `build_document_flow` (định tuyến effective_policy, heading level, interleave figure theo top) → Task 1. ✓
- B `render_flow_html` (semantic, data-span, image_block/figure, escape) → Task 2. ✓
- C endpoint `/flow?lang=` (ráp model_json + translations) → Task 3. ✓
- Verify thật → Task 4. ✓
- Kiểm thử model/renderer/endpoint → Task 1/2/3. ✓
- Ngoài phạm vi (section/nav F2, frontend F3, per-section F4, đa cột) → tôn trọng. ✓

**Placeholder scan:** không TBD; mọi step có code/lệnh. ✓

**Type consistency:**
- `FlowElement(kind, span_id=None, level=0, src=None)` — Task 1; dùng ở renderer Task 2 (`el.kind/.span_id/.level/.src`) và test. ✓
- `build_document_flow(pages) -> list[FlowElement]` — Task 1; gọi ở endpoint Task 3. ✓
- `render_flow_html(flow, translations, image_url_base) -> str` — Task 2; gọi ở endpoint Task 3. ✓
- `effective_policy(page_class, cover, override)` — dùng ở Task 1. ✓
- kind values {heading,paragraph,caption,list,figure,image_block} nhất quán model↔renderer↔test. ✓
