# Clean-Page Reconstruction — Pha 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bỏ ghost trên trang nội dung bằng cách: với chính sách nền `base-color`, renderer KHÔNG vẽ raster gốc (có chữ nung sẵn) và bỏ box scrim per-block — chữ dịch nằm trên nền sạch.

**Architecture:** Một hàm thuần `resolve_background_policy(page_class, cover)` ánh xạ nhãn #0 sang `base-color`/`keep-raster`/`clean-photo`. `render_text_layer` đọc policy: chỉ vẽ `<img class="tl-bg">` và box per-block khi policy ≠ `base-color`. Không gọi AI (clean-photo Pha 1 tạm vẽ raster như keep-raster). Không đổi extraction, schema DB, hay nhãn #0.

**Tech Stack:** Python 3, pytest. Làm việc trong `apps/break_the_barriers/backend`, chạy test bằng `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-04-clean-page-reconstruction-phase1-design.md`

## File Structure

- `app/services/background_policy.py` — **mới**; `resolve_background_policy` (thuần).
- `app/services/text_layer_renderer.py` — routing nền: bỏ raster + box khi `base-color`.
- Tests: `tests/test_background_policy.py` (mới); bổ sung `tests/test_text_layer_renderer.py`.

**Lưu ý chạy lệnh:** test chạy từ `apps/break_the_barriers/backend` bằng `.venv/bin/pytest`; git chạy từ repo root `/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator`. Import dùng `backend.app.services...`.

**Bối cảnh code hiện tại của `render_text_layer`** (`app/services/text_layer_renderer.py`) để khớp khi sửa:
- Khoảng dòng 52-58: tính `bg`, rồi `image_name = (model.background or {}).get("image")`; nếu `image_name` thì `parts.append('<img class="tl-bg" src=...>')`.
- Trong vòng `for blk in model.blocks:` (~dòng 82-96): tính `box = blk.box or None`, build `box_css` (fill/scrim), rồi append `<div class="tl-text" ... {box_css}>`.

---

### Task 1: `resolve_background_policy` (hàm thuần)

**Files:**
- Create: `app/services/background_policy.py`
- Test: `tests/test_background_policy.py`

- [ ] **Step 1: Viết test thất bại** — tạo `tests/test_background_policy.py`:

```python
from backend.app.services.background_policy import resolve_background_policy


def test_text_page_is_base_color():
    assert resolve_background_policy("text", "none") == "base-color"


def test_regenerable_content_page_is_base_color():
    # Trang nội dung có ảnh nền trang trí (vd mục lục trang 2).
    assert resolve_background_policy("regenerable", "none") == "base-color"


def test_preserve_keeps_raster():
    assert resolve_background_policy("preserve", "none") == "keep-raster"


def test_front_cover_is_clean_photo():
    assert resolve_background_policy("regenerable", "front") == "clean-photo"


def test_back_cover_is_clean_photo():
    assert resolve_background_policy("regenerable", "back") == "clean-photo"


def test_unknown_defaults_to_keep_raster():
    assert resolve_background_policy("something-else", "none") == "keep-raster"
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_background_policy.py -v` → `ModuleNotFoundError: background_policy`.

- [ ] **Step 3: Cài đặt.** Tạo `app/services/background_policy.py`:

```python
"""Resolve a page's background treatment from its #0 eligibility labels.

base-color  -> render on the document base color (drop the text-baked raster);
               kills the ghost on content pages.
keep-raster -> keep the original raster exactly (diagrams/charts/tables).
clean-photo -> ideal: AI removes baked-in text and keeps the photo (Phase 2).
               Phase 1 has no AI, so the renderer treats clean-photo like
               keep-raster (cover stays raster, ghost remains on covers only)."""
from __future__ import annotations


def resolve_background_policy(page_class: str, cover: str) -> str:
    if page_class == "preserve":
        return "keep-raster"
    if page_class == "regenerable":
        if cover in ("front", "back"):
            return "clean-photo"
        return "base-color"
    if page_class == "text":
        return "base-color"
    return "keep-raster"   # safe default for unknown labels
```

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_background_policy.py -v` → 6 passed.

- [ ] **Step 5: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/background_policy.py \
        apps/break_the_barriers/backend/tests/test_background_policy.py
git commit -m "feat(cleanpage): resolve_background_policy from #0 labels"
```

---

### Task 2: `render_text_layer` đọc policy (bỏ raster + box khi base-color)

**Files:**
- Modify: `app/services/text_layer_renderer.py`
- Test: `tests/test_text_layer_renderer.py` (bổ sung)

- [ ] **Step 1: Viết test thất bại** — thêm vào cuối `tests/test_text_layer_renderer.py` (file đã import `FontSpec, Block, Figure, PageModel` và `render_text_layer`):

```python
def _raster_model(page_class, cover):
    return PageModel(
        page_w=595.0, page_h=842.0, kind="mixed",
        background={"color": "#3c84bf", "image": "page-2.png"},
        blocks=[Block(span_id="s1", role="body", bbox=[70, 480, 300, 14],
                      text="", font=FontSpec(11, 400, False, "#000", "left", "sans"),
                      box={"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})],
        figures=[],
        page_class=page_class, cover=cover,
    )


def test_base_color_page_omits_raster_and_box():
    # regenerable + cover none -> base-color -> no raster, no per-block box.
    html = render_text_layer(_raster_model("regenerable", "none"),
                             {"s1": "Mục lục"}, image_url_base="http://api/assets")
    assert 'class="tl-bg"' not in html          # raster dropped
    assert "page-2.png" not in html
    assert "rgba(255,255,255,0.55)" not in html  # per-block scrim dropped
    assert "Mục lục" in html                     # translated text still rendered


def test_preserve_page_keeps_raster_and_box():
    # preserve -> keep-raster -> raster + box retained (no regression).
    html = render_text_layer(_raster_model("preserve", "none"),
                             {"s1": "X"}, image_url_base="http://api/assets")
    assert 'class="tl-bg"' in html
    assert "page-2.png" in html
    assert "rgba(255,255,255,0.55)" in html


def test_front_cover_keeps_raster_phase1():
    # regenerable + front -> clean-photo -> Phase 1 still draws raster.
    html = render_text_layer(_raster_model("regenerable", "front"),
                             {"s1": "X"}, image_url_base="http://api/assets")
    assert 'class="tl-bg"' in html
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_text_layer_renderer.py -k "base_color or keeps_raster or cover_keeps" -v` → `test_base_color_page_omits_raster_and_box` FAIL (raster + box vẫn xuất hiện).

- [ ] **Step 3: Cài đặt.** Trong `app/services/text_layer_renderer.py`:

(a) Thêm import ở đầu file (cạnh import `fit_font_size`):
```python
from backend.app.services.background_policy import resolve_background_policy
```

(b) Trong `render_text_layer`, ngay sau khi tính `bg = (model.background or {}).get("color") or "#ffffff"`, thêm:
```python
    policy = resolve_background_policy(model.page_class, model.cover)
    draw_raster = policy != "base-color"
```

(c) Sửa khối vẽ raster (hiện: `image_name = (model.background or {}).get("image")` rồi `if image_name:`). Đổi điều kiện thành:
```python
    image_name = (model.background or {}).get("image")
    if image_name and draw_raster:
        bg_src = html_lib.escape(f"{image_url_base}/{image_name}", quote=True)
        parts.append(f'<img class="tl-bg" src="{bg_src}" alt="page"/>')
```

(d) Trong vòng `for blk in model.blocks:`, sửa chỗ build `box_css` để khi `base-color` thì bỏ box. Đoạn hiện tại:
```python
        box = blk.box or None
        box_css = ""
        if box and box.get("fill"):
            if box.get("mode") == "scrim":
                box_css = f"background:{box['fill']};padding:0 2px;"
            else:
                box_css = f"background:{box['fill']};"
```
Đổi điều kiện ngoài cùng để gate theo `draw_raster`:
```python
        box = blk.box or None
        box_css = ""
        if box and box.get("fill") and draw_raster:
            if box.get("mode") == "scrim":
                box_css = f"background:{box['fill']};padding:0 2px;"
            else:
                box_css = f"background:{box['fill']};"
```

Không đổi gì khác (figures, slot-fit L3, script, chữ ký hàm).

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_text_layer_renderer.py -v` → tất cả pass (test cũ + 3 test mới).

- [ ] **Step 5: Full suite không hồi quy** — `.venv/bin/pytest tests/ -q --ignore=tests/test_extractor_box.py --ignore=tests/test_extractor_overhaul.py --ignore=tests/test_extractor_pagemodel.py` → tất cả pass. Chú ý `tests/test_text_layer_l2.py` và `tests/test_page_renderer.py` (các test này dựng PageModel mặc định `page_class="text"` → policy `base-color` → có thể KHÔNG còn vẽ raster). Nếu một test L2 cũ kỳ vọng `tl-bg` trên một model `kind=mixed` nhưng `page_class` mặc định `text`, đó là tương tác policy mới hợp lệ: cập nhật test đó để set `page_class="preserve"` (giữ raster) cho đúng ý nghĩa, KHÔNG nới lỏng logic. Báo lại test nào phải chỉnh và lý do.

- [ ] **Step 6: Commit**
```bash
git add apps/break_the_barriers/backend/app/services/text_layer_renderer.py \
        apps/break_the_barriers/backend/tests/test_text_layer_renderer.py
git commit -m "feat(cleanpage): render base-color pages without raster/box (kill ghost)"
```

---

### Task 3: Xác minh thật trên trang 2 (manual)

**Files:** không (chỉ verify).

Backend đang chạy `--reload` (port 8000) nên tự nạp code mới. Nhãn #0 cần có trong `model_json` của DB để policy hoạt động qua API. Lưu ý: backfill ở #0 chỉ sửa file đĩa, KHÔNG sửa DB. Vì vậy xác minh theo 2 lớp:

- [ ] **Step 1: Unit-level (render trực tiếp từ file model.json đã backfill).**
```bash
cd apps/break_the_barriers/backend && PYTHONPATH=/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers .venv/bin/python -c "
from backend.app.services.page_model import PageModel
from backend.app.services.page_renderer import render_page
pm = PageModel.from_json(open('data/extracted_html/2024-wttc-introduction-to-ai/2024-wttc-introduction-to-ai-2.model.json', encoding='utf-8').read())
print('page_class=', pm.page_class, 'cover=', pm.cover)
html = render_page(pm, {b.span_id: 'X' for b in pm.blocks}, 'http://api/assets')
print('has tl-bg:', 'class=\"tl-bg\"' in html)
print('has page-2.png:', 'page-2.png' in html)
"
```
Expected: `page_class= regenerable cover= none`, `has tl-bg: False`, `has page-2.png: False` — raster bị bỏ ⇒ ghost không thể xảy ra.

- [ ] **Step 2: API/UI (nếu DB có nhãn).** Mở `http://localhost:3000/books/2024-wttc-introduction-to-ai/preview` trang 2, hard-refresh (⌘⇧R). NẾU DB `model_json` chưa có nhãn #0 (page_class mặc định "text"), trang 2 vẫn ra `base-color` (vì text→base-color) → ghost vẫn hết. Xác nhận trang 2 không còn bóng đôi; chữ mục lục nằm trên nền (màu nền tài liệu), không đè raster. Báo lại quan sát (doc/page đã xem).

---

## Self-Review

**Spec coverage:**
- Chính sách nền 3 giá trị + bảng ánh xạ → Task 1. ✓
- `render_text_layer` bỏ raster khi base-color → Task 2 (c). ✓
- Bỏ box per-block khi base-color → Task 2 (d). ✓
- Figures + chữ vẽ mọi policy; chữ ký không đổi → Task 2 (không đụng figure/script). ✓
- Giữ raster cho preserve + clean-photo Pha 1 → Task 2 test_preserve / test_front_cover. ✓
- Kiểm thử resolve_background_policy (6 ca) + renderer (3 ca) → Task 1, Task 2. ✓
- Verify trang 2 hết ghost → Task 3. ✓
- Ngoài phạm vi (không AI, không TOC structure, không đổi extraction/DB/#0) → tôn trọng. ✓

**Placeholder scan:** không TBD/TODO; mọi step có code/lệnh cụ thể. ✓

**Type consistency:**
- `resolve_background_policy(page_class: str, cover: str) -> str` — định nghĩa Task 1, gọi ở Task 2 (b) với `model.page_class`/`model.cover` (field có từ #0). ✓
- `draw_raster = policy != "base-color"` dùng nhất quán ở Task 2 (c) và (d). ✓
- `PageModel(..., page_class=, cover=)` — field từ #0 đã merge trong nhánh hiện tại. ✓
