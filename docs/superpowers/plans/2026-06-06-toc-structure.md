# TOC Structure Rendering Implementation Plan (#3b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trên trang mục lục, render mỗi mục thành cấu trúc flex (tiêu đề trái · chấm dẫn CSS · số trang phải) thay cho chấm literal trong chữ — hết wrap/đè, có chấm dẫn + số căn phải.

**Architecture:** Module thuần `toc_parser` (`parse_toc_entry` tách tiêu đề/số; `is_toc_page` ≥3 mục → trang TOC). `render_text_layer` chỉ trên trang TOC mới đổi block khớp sang HTML flex `tl-toc`; trang/block khác giữ nguyên.

**Tech Stack:** Python 3, pytest, HTML/CSS. Backend `apps/break_the_barriers/backend`, test `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-06-toc-structure-design.md`

## File Structure

- `app/services/toc_parser.py` — **mới**; `parse_toc_entry` + `is_toc_page` (thuần).
- `app/services/text_layer_renderer.py` — CSS `.tl-toc*` + nhánh render TOC.
- Tests: `tests/test_toc_parser.py` (mới); bổ sung `tests/test_text_layer_renderer.py`.

**Lệnh:** test từ `apps/break_the_barriers/backend` (`.venv/bin/pytest`); git từ repo root. Nhánh `feat/manual-per-page` (đã checkout — KHÔNG tạo nhánh). Import `backend.app...`.

Ngữ cảnh code:
- `_CSS` có `.tl-text { ... }` ở dòng 41.
- Import services ở dòng 9-11.
- Block div emit (dòng 150-157):
```python
        parts.append(
            f'<div class="tl-text" data-fit="1" '
            f'data-span="{html_lib.escape(blk.span_id, quote=True)}" '
            f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
            f'width:{_pct(w, pw):.3f}%;'
            f'min-height:{_pct(h, ph):.3f}%;max-height:{_pct(max_h, ph):.3f}%;'
            f'font-family:{family};font-size:{size:.1f}px;font-weight:{weight};'
            f'font-style:{italic};color:{color};text-align:{align};{box_css}">'
            f'{html_lib.escape(text)}</div>'
        )
```

---

### Task 1: `toc_parser.py`

**Files:**
- Create: `app/services/toc_parser.py`
- Test: `tests/test_toc_parser.py`

- [ ] **Step 1: Viết test thất bại** — tạo `tests/test_toc_parser.py`:

```python
from backend.app.services.toc_parser import parse_toc_entry, is_toc_page


def test_dotted_entry():
    assert parse_toc_entry("Tiêu đề......3") == ("Tiêu đề", "3")


def test_tab_entry():
    assert parse_toc_entry("Thuật toán : Bộ não của AI\t 8") == ("Thuật toán : Bộ não của AI", "8")


def test_ellipsis_entry():
    assert parse_toc_entry("FOREWORD…… 4") == ("FOREWORD", "4")


def test_sentence_with_trailing_number_is_none():
    assert parse_toc_entry("một sự kiện trong năm 2023.") is None


def test_no_number_is_none():
    assert parse_toc_entry("MỤC LỤC") is None


def test_empty_is_none():
    assert parse_toc_entry("") is None


def test_is_toc_page_true_when_three_plus():
    texts = ["A....1", "B....2", "C....3", "MỤC LỤC", "footer |"]
    assert is_toc_page(texts) is True


def test_is_toc_page_false_for_normal_body():
    texts = ["Một đoạn văn bình thường.", "Đoạn nữa kết thúc 2023.", "MỤC LỤC"]
    assert is_toc_page(texts) is False
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_toc_parser.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Cài đặt.** Tạo `app/services/toc_parser.py`:

```python
"""Parse table-of-contents entries ("Title ..... 12") and detect TOC pages.

Pure, language-neutral: relies on a leader run (3+ dots, ellipsis chars, or a
tab) followed by a trailing page number — specific enough to avoid matching an
ordinary sentence that merely ends in a number."""
from __future__ import annotations
import re

_TOC_RE = re.compile(
    r'^(?P<title>.*?)\s*(?:\.{3,}|…+|\t)[\s.…]*(?P<num>\d+)\s*$')


def parse_toc_entry(text: str):
    """Return (title, page_num) for a TOC line, else None."""
    if not text:
        return None
    m = _TOC_RE.match(text)
    if not m:
        return None
    title = m.group("title").strip()
    if not title:
        return None
    return (title, m.group("num"))


def is_toc_page(block_texts, *, min_entries: int = 3) -> bool:
    """True when at least `min_entries` of the block texts parse as TOC lines."""
    return sum(1 for t in block_texts if parse_toc_entry(t)) >= min_entries
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_toc_parser.py -v` → 8 passed.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/toc_parser.py \
        apps/break_the_barriers/backend/tests/test_toc_parser.py
git commit -m "feat(#3b): toc_parser (parse_toc_entry + is_toc_page)"
```

---

### Task 2: Renderer — nhánh TOC flex + CSS

**Files:**
- Modify: `app/services/text_layer_renderer.py`
- Test: `tests/test_text_layer_renderer.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_text_layer_renderer.py`:

```python
def _toc_model():
    def blk(span, top):
        return Block(span_id=span, role="body", bbox=[72, top, 300, 14], text="",
                     font=FontSpec(11, 400, False, "#000", "left", "sans"))
    return PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#fff", "image": None},
        blocks=[blk("s1", 100), blk("s2", 120), blk("s3", 140),
                Block(span_id="hd", role="heading", bbox=[72, 60, 200, 24], text="",
                      font=FontSpec(24, 700, False, "#000", "left", "sans"))],
        figures=[], page_class="text", cover="none")


def test_toc_page_renders_flex_entries():
    html = render_text_layer(_toc_model(),
                             {"s1": "Lời nói đầu......3", "s2": "Giới thiệu......4",
                              "s3": "Thuật toán\t 8", "hd": "MỤC LỤC"},
                             image_url_base="http://api/a")
    assert 'class="tl-text tl-toc"' in html          # TOC entries got flex structure
    assert 'class="tl-toc-num">3<' in html           # page number broken out
    assert 'class="tl-toc-title">Lời nói đầu<' in html
    assert "......" not in html                        # literal dots gone
    # heading is NOT a TOC entry -> stays plain tl-text
    assert '>MỤC LỤC</div>' in html


def test_non_toc_page_unchanged():
    pm = PageModel(page_w=595.0, page_h=842.0, kind="text",
                   background={"color": "#fff", "image": None},
                   blocks=[Block(span_id="s1", role="body", bbox=[72, 100, 300, 14],
                                 text="", font=FontSpec(11, 400, False, "#000", "left", "sans"))],
                   figures=[], page_class="text", cover="none")
    html = render_text_layer(pm, {"s1": "Chỉ một mục......3"}, image_url_base="http://api/a")
    assert "tl-toc" not in html                        # <3 entries -> not a TOC page
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_text_layer_renderer.py -k "toc_page_renders or non_toc" -v` → FAIL (`tl-toc` chưa có).

- [ ] **Step 3a: Thêm import.** Dòng 11 (cạnh background_policy import), thêm:
```python
from backend.app.services.toc_parser import parse_toc_entry, is_toc_page
```

- [ ] **Step 3b: Thêm CSS.** Trong `_CSS`, ngay sau dòng `.tl-text { ... }` (dòng 41-42), thêm:
```python
.tl-toc { display: flex; align-items: flex-end; white-space: nowrap; }
.tl-toc-title { flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; }
.tl-toc-leader { flex: 1 1 8px; min-width: 8px; margin: 0 4px 3px;
                 border-bottom: 1px dotted currentColor; }
.tl-toc-num { flex: 0 0 auto; }
```
(Thêm vào trong chuỗi `_CSS` triple-quote, sau định nghĩa `.tl-text`.)

- [ ] **Step 3c: Tính `toc_page` trước vòng block.** Ngay trước `for blk in model.blocks:`, thêm:
```python
    toc_page = is_toc_page([(translations or {}).get(b.span_id, "") for b in model.blocks])
```

- [ ] **Step 3d: Nhánh nội dung TOC trong vòng block.** Ngay TRƯỚC lời gọi `parts.append(` (dòng ~150), thêm tính `cls` + `inner`:
```python
        entry = parse_toc_entry(text) if toc_page else None
        if entry:
            _title, _num = entry
            inner = (f'<span class="tl-toc-title">{html_lib.escape(_title)}</span>'
                     f'<span class="tl-toc-leader"></span>'
                     f'<span class="tl-toc-num">{html_lib.escape(_num)}</span>')
            cls = "tl-text tl-toc"
        else:
            inner = html_lib.escape(text)
            cls = "tl-text"
```
Rồi đổi `parts.append(...)` để dùng `{cls}` và `{inner}`:
```python
        parts.append(
            f'<div class="{cls}" data-fit="1" '
            f'data-span="{html_lib.escape(blk.span_id, quote=True)}" '
            f'style="left:{_pct(l, pw):.3f}%;top:{_pct(t, ph):.3f}%;'
            f'width:{_pct(w, pw):.3f}%;'
            f'min-height:{_pct(h, ph):.3f}%;max-height:{_pct(max_h, ph):.3f}%;'
            f'font-family:{family};font-size:{size:.1f}px;font-weight:{weight};'
            f'font-style:{italic};color:{color};text-align:{align};{box_css}">'
            f'{inner}</div>'
        )
```
(Chỉ đổi `class` và nội dung `{inner}`; mọi style/định vị giữ nguyên.)

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_text_layer_renderer.py -v` → tất cả pass (test cũ + 2 mới).

- [ ] **Step 5: Regression** — `.venv/bin/pytest tests/test_text_layer_renderer.py tests/test_text_layer_l2.py tests/test_page_renderer.py tests/test_toc_parser.py -q` → all pass.

- [ ] **Step 6: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/text_layer_renderer.py \
        apps/break_the_barriers/backend/tests/test_text_layer_renderer.py
git commit -m "feat(#3b): render TOC entries as flex (title/leader/num) on TOC pages"
```

---

### Task 3: Verify thật trang 2 (manual — controller)

**Files:** không.

- [ ] **Step 1:** Backend `--reload` đã có code mới. Chrome headless screenshot `pages/2?lang=vi&raw=true`.
- [ ] **Step 2:** Xác nhận mục lục: mỗi mục 1 dòng, chấm dẫn nối, số trang căn phải, KHÔNG đè/wrap. So với trước (đè). Gửi ảnh + báo cáo.

---

## Self-Review

**Spec coverage:**
- A `parse_toc_entry` (leader+num, None nếu không khớp) + `is_toc_page` (≥3) → Task 1. ✓
- B renderer chỉ đổi trên trang TOC, block khớp → flex; khác → thường → Task 2 (3c/3d). ✓
- C CSS `.tl-toc*` (flex, leader dotted, num phải) → Task 2 (3b). ✓
- Kiểm thử parser + renderer (TOC vs non-TOC, heading vẫn thường, hết chấm literal) → Task 1/2. ✓
- Verify trang 2 → Task 3. ✓
- Ngoài phạm vi (TOC đa cấp, số La Mã) → tôn trọng (regex chỉ `\d+`). ✓

**Placeholder scan:** không TBD; mọi step có code/lệnh. ✓

**Type consistency:**
- `parse_toc_entry(text) -> (title, num) | None`; `is_toc_page(texts, *, min_entries=3) -> bool` — Task 1; dùng ở renderer Task 2 (`entry = parse_toc_entry(text)`, `toc_page = is_toc_page([...])`). ✓
- `cls`/`inner` dùng nhất quán trong `parts.append`. ✓
- class CSS `tl-toc`/`tl-toc-title`/`tl-toc-leader`/`tl-toc-num` khớp giữa CSS (3b) và HTML (3d) và test. ✓
