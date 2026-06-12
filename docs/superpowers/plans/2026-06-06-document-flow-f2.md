# Sections + Synced Contents Nav (F2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap flow content into `<section>`s with stable anchors, and render one synced clickable Contents (mục lục) generated from the actual headings — replacing the original OCR'd TOC entries — so the table of contents can never drift from the real sections.

**Architecture:** Rewrite `flow_renderer.render_flow_html` to: collect headings (single source), wrap each heading's content in `<section id="sec-{span}">`, emit a generated `<nav class="fl-contents">` of anchor links at the original-TOC position, and suppress the original TOC entries (detected via `parse_toc_entry`).

**Tech Stack:** Python 3, pytest, HTML/CSS. Backend `apps/break_the_barriers/backend`, test `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-06-document-flow-f2-design.md`

## File Structure

- `app/services/flow_renderer.py` — rewrite `render_flow_html` (sections + contents + suppress TOC) + helpers + CSS.
- Test: bổ sung `tests/test_flow_renderer.py`.

**Lệnh:** test từ `apps/break_the_barriers/backend` (`.venv/bin/pytest`); git từ repo root. Nhánh `feat/document-flow` (đã checkout — KHÔNG tạo nhánh). Import `backend.app...`.

Hiện trạng: `flow_renderer.py` có `render_flow_html(flow, translations, image_url_base)` (F1) render phẳng; `_CSS`/`_FONTS` đã có; `FlowElement{kind,span_id,level,src}`. `toc_parser.parse_toc_entry(text)` có sẵn.

---

### Task 1: Rewrite render_flow_html — sections + synced contents

**Files:**
- Modify: `app/services/flow_renderer.py`
- Test: `tests/test_flow_renderer.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_flow_renderer.py`:

```python
import re as _re


def test_headings_wrapped_in_sections():
    flow = [FlowElement(kind="heading", span_id="h", level=1),
            FlowElement(kind="paragraph", span_id="p")]
    html = render_flow_html(flow, {"h": "Chương 1", "p": "Nội dung"},
                            image_url_base="http://api/a")
    assert '<section id="sec-h">' in html
    # heading + following paragraph live inside that section (paragraph after the h1)
    seg = html.split('<section id="sec-h">', 1)[1]
    assert "Chương 1" in seg and "Nội dung" in seg


def test_pre_heading_content_in_intro_section():
    flow = [FlowElement(kind="paragraph", span_id="p0"),
            FlowElement(kind="heading", span_id="h", level=1)]
    html = render_flow_html(flow, {"p0": "Mở đầu", "h": "Chương"},
                            image_url_base="http://api/a")
    assert '<section class="fl-intro">' in html
    assert '<section id="sec-h">' in html


def test_generated_contents_links_to_headings_and_suppresses_original_toc():
    flow = [FlowElement(kind="heading", span_id="a", level=1),
            FlowElement(kind="heading", span_id="b", level=2),
            FlowElement(kind="paragraph", span_id="toc1")]
    html = render_flow_html(
        flow, {"a": "Phần A", "b": "Phần B", "toc1": "Phần A......3"},
        image_url_base="http://api/a")
    assert '<nav class="fl-contents">' in html
    assert 'href="#sec-a"' in html and 'href="#sec-b"' in html
    assert "Phần A" in html and "Phần B" in html
    assert "......" not in html                      # original TOC dots suppressed


def test_every_contents_link_has_matching_section():
    flow = [FlowElement(kind="heading", span_id="a", level=1),
            FlowElement(kind="heading", span_id="b", level=1),
            FlowElement(kind="paragraph", span_id="t")]
    html = render_flow_html(flow, {"a": "A", "b": "B", "t": "A....1"},
                            image_url_base="http://api/a")
    hrefs = set(_re.findall(r'href="#(sec-[^"]+)"', html))
    ids = set(_re.findall(r'<section id="(sec-[^"]+)"', html))
    assert hrefs and hrefs <= ids                    # no dangling links


def test_no_toc_page_no_contents_block():
    flow = [FlowElement(kind="heading", span_id="h", level=1),
            FlowElement(kind="paragraph", span_id="p")]
    html = render_flow_html(flow, {"h": "H", "p": "Đoạn thường."},
                            image_url_base="http://api/a")
    assert 'class="fl-contents"' not in html
    assert '<section id="sec-h">' in html
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_flow_renderer.py -k "section or contents or matching_section or no_toc" -v` → FAIL (chưa có section/contents).

- [ ] **Step 3: Cài đặt.** Trong `app/services/flow_renderer.py`:

(a) Thêm import (cạnh import FlowElement):
```python
from backend.app.services.toc_parser import parse_toc_entry
```

(b) Thêm CSS vào cuối chuỗi `_CSS` (trước dấu `"""` đóng):
```css
.fl-doc section { scroll-margin-top: 16px; }
.fl-contents { margin: 1.5em 0; }
.fl-toc-link { display: flex; align-items: flex-end; text-decoration: none;
               color: inherit; margin: .25em 0; }
.fl-toc-link .t { flex: 0 1 auto; }
.fl-toc-dots { flex: 1 1 8px; min-width: 8px; margin: 0 4px 4px;
               border-bottom: 1px dotted #aaa; }
.fl-toc-link.lvl2 { margin-left: 1.5em; }
.fl-toc-link.lvl3 { margin-left: 3em; }
.fl-toc-link:hover .t { text-decoration: underline; }
```

(c) Thêm 2 helper trước `render_flow_html`:
```python
def _heading_entries(flow, translations):
    out = []
    for el in flow:
        if el.kind == "heading":
            text = (translations or {}).get(el.span_id)
            if text:
                out.append((el.span_id, el.level, text))
    return out


def _contents_html(headings) -> str:
    links = []
    for span, level, text in headings:
        lvl = level if level in (1, 2, 3) else 3
        sid = html_lib.escape(f"sec-{span}", quote=True)
        links.append(
            f'<a href="#{sid}" class="fl-toc-link lvl{lvl}">'
            f'<span class="t">{html_lib.escape(text)}</span>'
            f'<span class="fl-toc-dots"></span></a>')
    return f'<nav class="fl-contents">{"".join(links)}</nav>'
```

(d) Thay TOÀN BỘ thân `render_flow_html` bằng:
```python
def render_flow_html(flow: List[FlowElement], translations: dict,
                     image_url_base: str) -> str:
    headings = _heading_entries(flow, translations)
    contents_html = _contents_html(headings) if headings else ""
    parts: List[str] = []
    section_open = False
    contents_done = False

    def ensure_section():
        nonlocal section_open
        if not section_open:
            parts.append('<section class="fl-intro">')
            section_open = True

    for el in flow:
        text = (translations or {}).get(el.span_id) if el.span_id else None
        # Original TOC entry: suppress; emit the generated contents once in its place.
        if el.kind in ("paragraph", "caption", "list") and text and parse_toc_entry(text):
            ensure_section()
            if not contents_done and contents_html:
                parts.append(contents_html)
                contents_done = True
            continue
        if el.kind == "heading" and text:
            if section_open:
                parts.append("</section>")
            sid = html_lib.escape(f"sec-{el.span_id}", quote=True)
            parts.append(f'<section id="{sid}">')
            section_open = True
            lvl = el.level if el.level in (1, 2, 3) else 3
            span = html_lib.escape(el.span_id or "", quote=True)
            parts.append(f'<h{lvl} data-span="{span}">{html_lib.escape(text)}</h{lvl}>')
            continue
        if el.kind == "image_block" and el.src:
            ensure_section()
            src = html_lib.escape(f"{image_url_base}/{el.src}", quote=True)
            parts.append(f'<img class="fl-page" src="{src}" alt="page"/>')
            continue
        if el.kind == "figure" and el.src:
            ensure_section()
            src = html_lib.escape(f"{image_url_base}/{el.src}", quote=True)
            parts.append(f'<figure><img class="fl-fig" src="{src}" alt="figure"/></figure>')
            continue
        if not text:
            continue
        ensure_section()
        span = html_lib.escape(el.span_id or "", quote=True)
        body = html_lib.escape(text)
        if el.kind == "caption":
            parts.append(f'<p class="cap" data-span="{span}">{body}</p>')
        elif el.kind == "list":
            parts.append(f'<p class="li" data-span="{span}">• {body}</p>')
        else:
            parts.append(f'<p data-span="{span}">{body}</p>')
    if section_open:
        parts.append("</section>")
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'{_FONTS}<style>{_CSS}</style></head><body>'
        f'<article class="fl-doc">{"".join(parts)}</article></body></html>'
    )
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_flow_renderer.py -v` → tất cả pass (gồm 3 test F1 cũ + 5 mới). F1 cũ vẫn pass vì heading/p/figure/image_block giờ nằm trong section nhưng các assert cũ (`<h1`, `<p`, data-span, fl-fig, fl-page) vẫn đúng.

- [ ] **Step 5: Regression** — `.venv/bin/pytest tests/test_flow_model.py tests/test_flow_renderer.py tests/test_preview_pagemodel.py -q` → all pass (endpoint `/flow` test vẫn xanh).

- [ ] **Step 6: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/flow_renderer.py \
        apps/break_the_barriers/backend/tests/test_flow_renderer.py
git commit -m "feat(F2): sections + synced clickable contents (single source, suppress original TOC)"
```

---

### Task 2: Verify thật tài liệu flow có nav (manual — controller)

**Files:** không.

- [ ] **Step 1:** Backend `--reload` đã có code mới. `curl` đếm: `<section id="sec-`, `fl-contents`, `href="#sec-` trên `GET /api/docs/2024-wttc-introduction-to-ai/flow?lang=vi`; xác nhận mọi `href="#sec-X"` có `<section id="sec-X">` (0 lệch).
- [ ] **Step 2:** Chrome headless screenshot phần mục lục của `/flow`; xác nhận khối Contents sinh tự động (chấm dẫn, không số trang), không còn TOC gốc bẩn. Gửi ảnh + báo cáo.

---

## Self-Review

**Spec coverage:**
- A section + anchor (heading→`<section id=sec-span>`, intro section) → Task 1 (d). ✓
- B contents sinh từ headings + link `#sec-{id}` + thụt level → Task 1 (c/d) `_contents_html`. ✓
- Suppress TOC gốc + chèn contents tại vị trí TOC đầu → Task 1 (d) nhánh parse_toc_entry. ✓
- 0 lệch (link↔section) → Task 1 test `test_every_contents_link_has_matching_section`. ✓
- Không TOC page → không contents → test `test_no_toc_page_no_contents_block`. ✓
- CSS fl-contents/fl-toc-link/dots/lvl → Task 1 (b). ✓
- Verify thật → Task 2. ✓
- Ngoài phạm vi (sidebar F3, khớp-tên) → tôn trọng. ✓

**Placeholder scan:** không TBD; mọi step có code/lệnh. ✓

**Type consistency:**
- `_heading_entries(flow, translations) -> list[(span,level,text)]`; `_contents_html(headings) -> str` — dùng nhất quán trong `render_flow_html`. ✓
- anchor id `sec-{span_id}` khớp giữa `<section id>` và `href="#sec-{id}"`. ✓
- `parse_toc_entry(text)` (toc_parser) — gate suppress. ✓
- `FlowElement.kind/span_id/level/src` khớp F1. ✓
