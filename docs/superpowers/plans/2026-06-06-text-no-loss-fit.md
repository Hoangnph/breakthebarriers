# Text No-Loss Role-Based Fit Implementation Plan (#3a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Heading blocks fit to their original bbox height (shrink to stay ~1 line in their designed region) while body blocks keep L3 slot behavior — so longer translations don't wrap past their background and get lost.

**Architecture:** In `render_text_layer`'s block loop, pick the fit-target height and CSS `max-height` per `blk.role`: heading → bbox `h`; body/other → `slot_h` (current L3). `fit_font_size` itself is unchanged.

**Tech Stack:** Python 3, pytest. Backend `apps/break_the_barriers/backend`, test `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-06-text-no-loss-fit-design.md`

## File Structure

- `app/services/text_layer_renderer.py` — role-based fit target + max-height in the block loop.
- Test: `tests/test_text_layer_renderer.py` (bổ sung).

**Lệnh:** test từ `apps/break_the_barriers/backend` (`.venv/bin/pytest`); git từ repo root. Nhánh `feat/manual-per-page` (đã checkout — KHÔNG tạo nhánh). Import `backend.app...`.

Hiện trạng block loop (để khớp khi sửa):
```python
        slot_h = slots.get(blk.span_id, h)
        base = (f.size if f and f.size else max(8.0, h * 0.8))
        size = fit_font_size(text, w, slot_h, max_size=base, min_size=6.0,
                             height_growth=1.0)
        ...
            f'min-height:{_pct(h, ph):.3f}%;max-height:{_pct(slot_h, ph):.3f}%;'
```

---

### Task 1: Role-based fit target (heading → bbox, body → slot)

**Files:**
- Modify: `app/services/text_layer_renderer.py`
- Test: `tests/test_text_layer_renderer.py`

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_text_layer_renderer.py`:

```python
import re


def _two_block_heading_body():
    # Heading at top with a body block far below -> heading has a large slot.
    return PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#fff", "image": None},
        blocks=[
            Block(span_id="hd", role="heading", bbox=[72, 40, 200, 24], text="",
                  font=FontSpec(32, 700, False, "#000", "left", "sans")),
            Block(span_id="bd", role="body", bbox=[72, 200, 200, 100], text="",
                  font=FontSpec(11, 400, False, "#000", "left", "sans")),
        ], figures=[], page_class="text", cover="none")


def _maxmin(html, span):
    # return (min_height_pct, max_height_pct) strings for a given data-span
    m = re.search(r'data-span="%s"[^>]*min-height:([0-9.]+)%%;max-height:([0-9.]+)%%' % span, html)
    assert m, f"div for {span} not found"
    return m.group(1), m.group(2)


def test_heading_clamps_to_bbox_body_uses_slot():
    html = render_text_layer(_two_block_heading_body(),
                             {"hd": "Tiêu đề dài hơn nhiều", "bd": "Thân bài"},
                             image_url_base="http://api/assets")
    h_min, h_max = _maxmin(html, "hd")
    b_min, b_max = _maxmin(html, "bd")
    assert h_min == h_max          # heading clamped to its bbox (no slot growth)
    assert float(b_max) > float(b_min)   # body still uses the larger slot


def _font_px(html, span):
    m = re.search(r'data-span="%s"[^>]*font-size:([0-9.]+)px' % span, html)
    assert m
    return float(m.group(1))


def test_heading_shrinks_more_than_body_for_same_long_text():
    # Same long text + same geometry, heading (fit to bbox) shrinks <= body (fit to slot).
    long = "Một tiêu đề tiếng Việt khá là dài để buộc phải xuống dòng"
    def _one(role):
        return PageModel(page_w=595.0, page_h=842.0, kind="text",
                         background={"color": "#fff", "image": None},
                         blocks=[Block(span_id="s1", role=role, bbox=[72, 40, 150, 20],
                                       text="", font=FontSpec(28, 700, False, "#000", "left", "sans"))],
                         figures=[], page_class="text", cover="none")
    h_html = render_text_layer(_one("heading"), {"s1": long}, image_url_base="http://api/a")
    b_html = render_text_layer(_one("body"), {"s1": long}, image_url_base="http://api/a")
    assert _font_px(h_html, "s1") <= _font_px(b_html, "s1")
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_text_layer_renderer.py -k "heading_clamps or heading_shrinks" -v` → `test_heading_clamps_to_bbox_body_uses_slot` FAIL (heading hiện dùng slot → h_min != h_max).

- [ ] **Step 3: Cài đặt.** Trong `app/services/text_layer_renderer.py`, trong vòng `for blk in model.blocks:`, sửa khối tính fit + max-height. Đoạn hiện tại:
```python
        slot_h = slots.get(blk.span_id, h)
        base = (f.size if f and f.size else max(8.0, h * 0.8))
        size = fit_font_size(text, w, slot_h, max_size=base, min_size=6.0,
                             height_growth=1.0)
```
Đổi thành:
```python
        slot_h = slots.get(blk.span_id, h)
        # Headings fit to their original bbox (stay ~1 line in their designed
        # region/banner); body keeps the L3 slot growth to avoid tiny text.
        is_heading = blk.role == "heading"
        fit_h = h if is_heading else slot_h
        max_h = h if is_heading else slot_h
        base = (f.size if f and f.size else max(8.0, h * 0.8))
        size = fit_font_size(text, w, fit_h, max_size=base, min_size=6.0,
                             height_growth=1.0)
```
Và trong chuỗi style của div, đổi `max-height:{_pct(slot_h, ph):.3f}%` thành `max-height:{_pct(max_h, ph):.3f}%`:
```python
            f'min-height:{_pct(h, ph):.3f}%;max-height:{_pct(max_h, ph):.3f}%;'
```
(Không đổi gì khác: min-height vẫn = bbox `h`; figures, box_css, script giữ nguyên.)

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_text_layer_renderer.py -v` → tất cả pass (gồm test cũ + 2 mới). Đặc biệt xác nhận các test L3/clean-photo cũ vẫn pass (body vẫn dùng slot).

- [ ] **Step 5: Regression** — `.venv/bin/pytest tests/test_text_layer_renderer.py tests/test_text_layer_l2.py tests/test_page_renderer.py -q` → all pass.

- [ ] **Step 6: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/text_layer_renderer.py \
        apps/break_the_barriers/backend/tests/test_text_layer_renderer.py
git commit -m "fix(#3a): headings fit to bbox so long translations don't wrap off-region"
```

---

### Task 2: Verify thật tiêu đề trang 3 (manual — controller)

**Files:** không.

- [ ] **Step 1:** Backend `--reload` đã có code mới. Chrome headless screenshot `pages/3?lang=vi&raw=true`.
- [ ] **Step 2:** Xác nhận tiêu đề "LỜI NÓI ĐẦU" hiện ĐỦ (1 dòng, co nhỏ hơn, nằm trên banner) — không còn mất "ĐẦU". So với trước. Gửi ảnh + báo cáo.

---

## Self-Review

**Spec coverage:**
- heading fit về bbox `h` (target + max-height) → Task 1 Step 3. ✓
- body giữ slot (L3) → Task 1 (else nhánh) + test body max>min. ✓
- `fit_font_size` không đổi → chỉ đổi tham số truyền. ✓
- Kiểm thử: heading clamp (max==min), body slot (max>min), heading font ≤ body → Task 1 tests. ✓
- Verify tiêu đề trang 3 → Task 2. ✓
- Ngoài phạm vi (màu, TOC 3b) → tôn trọng. ✓

**Placeholder scan:** không TBD; mọi step có code/lệnh. ✓

**Type consistency:** `is_heading`/`fit_h`/`max_h` dùng nhất quán trong Task 1; `fit_font_size(text, w, fit_h, ...)` khớp chữ ký hiện có; `max-height` emit dùng `max_h`. min-height vẫn `h`. ✓
