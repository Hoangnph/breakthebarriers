# Classifier Tuning — Text-Dominant Pages Not `preserve` — Thiết kế

Ngày: 2026-06-05
Nhánh dự kiến: tiếp tục `feat/manual-per-page` (hoặc nhánh mới từ đó)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

Đây là việc **#1/3** trong nhóm hậu-verify (1. classifier tuning · 2. figure-có-chữ · 3. cấu trúc TOC).

## Bối cảnh & vấn đề

`page_eligibility.classify_page` hiện ép `preserve` (giữ NGUYÊN raster → ghost chữ
gốc) ngay khi trang có một figure `diagram`/`uncertain` hoặc một `table`, **bất
kể trang chủ yếu là chữ**. Verify thật trang FOREWORD (text≈31%, fig≈23%, có
figure diagram) → `preserve` → thân bài tiếng Việt bị đè lên chữ Anh nung sẵn.

Logic hiện tại:
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

## Insight

`preserve` (giữ cả raster) chỉ thật sự cần cho trang **figure-trội** — nơi sơ
đồ/biểu đồ là nội dung chính và "chữ" trích ra là nhãn nằm trong sơ đồ (overlay
bản dịch lên sẽ lệch). Với trang **chữ-trội** có figure, render `text`
(base-color) cho kết quả tốt hơn: thân bài sạch trên nền trắng, **figure vẫn
được crop riêng và render nguyên pixel** (renderer không overlay chữ lên figure)
→ vừa sạch thân bài, vừa bảo toàn sơ đồ. Tức đặc tính "không phá sơ đồ" vẫn giữ:
sơ đồ-dạng-figure được bảo toàn qua crop, không phải qua việc giữ cả raster.

## Thay đổi

Thêm một nhánh **chữ-trội** vào `classify_page`, đặt SAU nhánh `has_image`
early-return và TRƯỚC nhánh `preserve`:

```python
    if (text_ratio >= TEXT_DOMINANT_MIN and text_ratio >= fig_ratio
            and not has_table):
        return "text"
```

- `TEXT_DOMINANT_MIN = 0.15` (hằng số module) — tránh trang gần như trống.
- Guard chính: **`text_ratio >= fig_ratio`** (chữ phủ ≥ figure) → chỉ trang
  chữ-trội mới vào nhánh này.
- **`has_table` vẫn rơi xuống `preserve`** (giữ lưới bảng trong raster — overlay
  chữ trên nền trắng sẽ mất khung bảng).

### Ma trận hành vi
| Trang | text/fig | có | Trước | Sau |
|---|---|---|---|---|
| FOREWORD (chữ-trội + diagram figure) | 0.31 / 0.23 | diagram | preserve | **text** ✓ |
| Sơ đồ-trội | 0.07 / 0.80 | diagram | preserve | preserve ✓ (text<fig) |
| Bảng (chữ-trội + table) | 0.40 / 0.10 | table | preserve | preserve ✓ (has_table) |
| Trang chữ + ảnh | 0.50 / 0.20 | photo | preserve | **text** (hành vi MỚI mong muốn) |
| Bìa ảnh ít chữ | 0.10 / 0.50 | photo | regenerable | regenerable ✓ (text<fig) |

## An toàn / không hồi quy

- Đặc tính "sơ đồ không bao giờ bị regenerate/phá": giữ nguyên — trang figure-trội
  có diagram vẫn `preserve`; sơ đồ-dạng-figure trên trang chữ-trội được bảo toàn
  qua crop (renderer chỉ overlay lên text block, không lên figure).
- Renderer KHÔNG đổi: trang `text` → base-color (đã render figure crop + chữ dịch).
- Không đổi schema DB, không đổi extraction. Cần **backfill lại nhãn** (chạy
  `scripts/relabel_document.py`) để trang đã extract nhận nhãn mới; hoặc dùng
  manual override (#3) cho từng trang. (Backfill không thuộc thay đổi code này.)

## Tác động test #0

`tests/test_page_eligibility.py::test_text_heavy_page_with_photo_is_preserve`
(text 0.5 + photo, kỳ vọng `preserve`) sẽ đổi thành kỳ vọng **`text`** — đúng
hành vi mới. Cập nhật/đổi tên test này (vd `test_text_heavy_page_with_photo_is_text`).

## Kiểm thử (TDD)

- `classify_page(0.31, 0.23, ["diagram"], has_table=False, bg_is_photo=False) == "text"`
  (chữ-trội + diagram → text).
- `classify_page(0.07, 0.80, ["diagram"], ...) == "preserve"` (figure-trội giữ).
- `classify_page(0.40, 0.10, [], has_table=True, ...) == "preserve"` (bảng giữ).
- `classify_page(0.10, 0.50, ["photo","photo"], ...) == "regenerable"` (bìa ảnh — không đổi).
- Cập nhật test text-heavy+photo → `text`.

## Ngoài phạm vi

- Figure có chữ nung (banner FOREWORD) — việc #2.
- Cấu trúc TOC — việc #3.
- Backfill/relabel tự động vào DB.

## Các file đụng tới

- Sửa: `app/services/page_eligibility.py` (thêm nhánh + hằng `TEXT_DOMINANT_MIN`).
- Test: `tests/test_page_eligibility.py` (thêm ca + cập nhật ca text-heavy).
