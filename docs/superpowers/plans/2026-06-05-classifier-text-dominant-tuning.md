# Classifier Text-Dominant Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trang chữ-trội (text_ratio ≥ fig_ratio, không bảng) được phân `text` (base-color, thân bài sạch + figure crop) thay vì `preserve` (giữ raster → ghost), trong khi trang figure-trội/bảng vẫn `preserve`.

**Architecture:** Thêm một nhánh "chữ-trội" vào hàm thuần `classify_page` (page_eligibility.py), đặt trước nhánh `preserve`. Verify trên doc thật bằng cách re-classify nhãn 3 trang đầu vào DB rồi so sánh 3 góc nhìn Gốc/HTML/Dịch.

**Tech Stack:** Python 3, pytest; Chrome headless cho screenshot. Backend `apps/break_the_barriers/backend`, test `.venv/bin/pytest`.

---

## Spec

`docs/superpowers/specs/2026-06-05-classifier-text-dominant-tuning-design.md`

## File Structure

- `app/services/page_eligibility.py` — thêm nhánh chữ-trội + kwarg `text_dominant_min`.
- Test: `tests/test_page_eligibility.py` — thêm ca + cập nhật ca text-heavy+photo.

**Lệnh:** test từ `apps/break_the_barriers/backend` (`.venv/bin/pytest`); git từ repo root. Nhánh `feat/manual-per-page` (đã checkout — KHÔNG tạo nhánh). Import `backend.app...`.

Hiện trạng `classify_page` (để khớp khi sửa):
```python
def classify_page(text_ratio, fig_ratio, figure_labels, *, has_table, bg_is_photo,
                  text_max=0.30, fig_min=0.15):
    has_image = bg_is_photo or fig_ratio >= fig_min or bool(figure_labels)
    if not has_image and text_ratio > 0:
        return "text"
    if has_table or any(lbl in ("diagram", "uncertain") for lbl in figure_labels):
        return "preserve"
    if text_ratio < text_max and has_image and all(lbl == "photo" for lbl in figure_labels):
        return "regenerable"
    return "preserve"
```

---

### Task 1: Nhánh chữ-trội trong `classify_page`

**Files:**
- Modify: `app/services/page_eligibility.py`
- Test: `tests/test_page_eligibility.py`

- [ ] **Step 1: Cập nhật + thêm test (red).**
  (a) Trong `tests/test_page_eligibility.py`, ĐỔI test cũ `test_text_heavy_page_with_photo_is_preserve` thành hành vi mới — đổi tên + kỳ vọng:
  ```python
  def test_text_heavy_page_with_photo_is_text():
      # Trang chữ nhiều + 1 ảnh → render text (base-color), figure vẫn crop.
      assert classify_page(0.5, 0.2, ["photo"], has_table=False, bg_is_photo=False) == "text"
  ```
  (Xóa/đổi tên bản cũ `..._is_preserve` — không để lại cả hai.)

  (b) Thêm các test mới:
  ```python
  def test_text_dominant_with_diagram_is_text():
      # FOREWORD: chữ-trội (0.31 >= 0.23) + diagram figure → text (thân bài sạch).
      assert classify_page(0.31, 0.23, ["diagram"], has_table=False, bg_is_photo=False) == "text"


  def test_figure_dominant_diagram_still_preserve():
      # Sơ đồ-trội (text < fig) → giữ raster.
      assert classify_page(0.07, 0.80, ["diagram"], has_table=False, bg_is_photo=False) == "preserve"


  def test_text_dominant_with_table_still_preserve():
      # Có bảng → giữ raster (lưới bảng).
      assert classify_page(0.40, 0.10, [], has_table=True, bg_is_photo=False) == "preserve"


  def test_sparse_text_with_diagram_not_text():
      # Chữ quá ít (< TEXT_DOMINANT_MIN) dù >= fig vẫn không vào nhánh text.
      assert classify_page(0.10, 0.05, ["diagram"], has_table=False, bg_is_photo=False) == "preserve"
  ```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `.venv/bin/pytest tests/test_page_eligibility.py -k "text_heavy or text_dominant or figure_dominant_diagram or sparse_text" -v` → các ca mới FAIL (đặc biệt text_dominant_with_diagram trả `preserve`).

- [ ] **Step 3: Cài đặt.** Trong `app/services/page_eligibility.py`, sửa chữ ký thêm kwarg và thêm nhánh chữ-trội SAU `has_image` early-return, TRƯỚC nhánh `preserve`:
  ```python
  def classify_page(text_ratio, fig_ratio, figure_labels, *, has_table, bg_is_photo,
                    text_max=0.30, fig_min=0.15, text_dominant_min=0.15):
      has_image = bg_is_photo or fig_ratio >= fig_min or bool(figure_labels)
      if not has_image and text_ratio > 0:
          return "text"
      # Text-dominant page (text covers >= figures, no table): render as text so the
      # body is clean; figures are still cropped & preserved by the renderer.
      if (text_ratio >= text_dominant_min and text_ratio >= fig_ratio
              and not has_table):
          return "text"
      if has_table or any(lbl in ("diagram", "uncertain") for lbl in figure_labels):
          return "preserve"
      if text_ratio < text_max and has_image and all(lbl == "photo" for lbl in figure_labels):
          return "regenerable"
      return "preserve"
  ```
  Lưu ý: nhánh mới đặt trước cả `has_table`/`preserve` nhưng đã loại `has_table` trong điều kiện (bảng vẫn rơi xuống preserve). `regenerable` cho bìa ảnh (text < fig) không bị ảnh hưởng vì nhánh mới yêu cầu `text >= fig`.

- [ ] **Step 4: Chạy để xác nhận PASS** — `.venv/bin/pytest tests/test_page_eligibility.py -v` → tất cả pass (gồm các ca #0 cũ còn lại + ca mới). Đặc biệt xác nhận `test_all_photo_low_text_is_regenerable` (0.1/0.5) vẫn `regenerable` và `test_diagram_figure_forces_preserve` (0.1/0.5) vẫn `preserve`.

- [ ] **Step 5: Commit**
  ```bash
  git add apps/break_the_barriers/backend/app/services/page_eligibility.py \
          apps/break_the_barriers/backend/tests/test_page_eligibility.py
  git commit -m "feat(classifier): text-dominant pages classify as text, not preserve"
  ```

---

### Task 2: Verify chất lượng 3 trang đầu (manual — controller)

**Files:** không (verify + so sánh trực quan dưới góc nhìn độc giả).

Vì classifier chạy lúc extract, doc đã extract cần re-classify nhãn vào DB để thấy hiệu lực. Controller làm one-off (không phải feature shipped).

- [ ] **Step 1: Re-classify nhãn 3 trang đầu vào DB.** Controller chạy script tính lại `page_class`/`cover` từ `classify_page`/`detect_cover` (giống `relabel_document` nhưng ghi vào `DBPage.model_json`) cho `2024-wttc-introduction-to-ai` trang 1–3, dùng `bg_is_photo` xấp xỉ (có ảnh nền + kind≠text), figure labels từ `picture_classifier` trên crop. In ra page_class mới mỗi trang (kỳ vọng: p1=preserve/cover front→clean-photo policy; p3 chuyển `preserve`→`text`).

- [ ] **Step 2: Chụp 3 góc nhìn cho mỗi trang 1–3.** Với mỗi trang n:
  - **Gốc**: đọc trực tiếp raster gốc `data/extracted_html/<doc>/page-n.png` (ảnh trang gốc, chữ Anh nung sẵn).
  - **HTML**: Chrome headless screenshot `pages/n?lang=en&raw=true`.
  - **Dịch**: Chrome headless screenshot `pages/n?lang=vi&raw=true`.
  (Chrome: `--headless=new --virtual-time-budget=6000 --window-size=820,1160 --force-device-scale-factor=2`.)

- [ ] **Step 3: Tự đánh giá dưới góc nhìn độc giả** từng trang (đặc biệt mục lục trang 2 + title trang 1), so sánh Gốc ↔ HTML ↔ Dịch: bố cục có giữ? chữ có sạch/không ghost? mục lục có đọc được (chấm dẫn, số trang)? title có đúng vị trí? Nêu rõ ĐẠT/CHƯA ĐẠT từng trang + vấn đề còn lại (dự kiến: trang 2 TOC còn wrap; trang 3 banner còn chữ nung → thuộc việc #2/#3).

- [ ] **Step 4: Gửi ảnh + báo cáo** cho người dùng; nếu p3 thân bài đã sạch sau tuning → xác nhận #1 đạt mục tiêu.

---

## Self-Review

**Spec coverage:**
- Nhánh chữ-trội (text ≥ fig, không table, ≥ min) → text → Task 1 Step 3. ✓
- has_table vẫn preserve; figure-trội vẫn preserve; bìa ảnh vẫn regenerable → Task 1 tests. ✓
- Cập nhật test #0 text-heavy+photo → text → Task 1 Step 1(a). ✓
- Verify 3 trang đầu, so sánh Gốc/HTML/Dịch góc nhìn độc giả → Task 2. ✓
- Ngoài phạm vi (figure-có-chữ #2, TOC #3, backfill-DB feature) → tôn trọng (Task 2 relabel là one-off verify, không ship). ✓

**Placeholder scan:** không TBD; mọi step có code/lệnh. ✓

**Type consistency:** `classify_page(..., text_dominant_min=0.15)` — kwarg mới, các call-site hiện có (extractor, relabel script) không truyền nên dùng default; không vỡ. Giá trị trả vẫn {text, preserve, regenerable}. ✓
