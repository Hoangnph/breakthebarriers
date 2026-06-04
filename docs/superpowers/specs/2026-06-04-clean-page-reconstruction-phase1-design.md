# Clean-Page Reconstruction — Pha 1 (no-AI) — Thiết kế

Ngày: 2026-06-04
Nhánh dự kiến: nối tiếp `feat/page-eligibility-classifier` (build trên nhãn #0)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

## Bối cảnh & vấn đề

Trên các trang non-`text` (vd trang 2 — mục lục nằm trên ảnh full-bleed), bản
preview bị **hai lỗi**:

1. **Ghost (bóng đôi):** raster gốc (`page-{n}.png`) đã có chữ tiếng Anh **nung
   sẵn trong ảnh**. Renderer vẽ raster đó làm nền rồi phủ chữ overlay qua một
   lớp **scrim chỉ 55% mờ** (`rgba(255,255,255,0.55)`) — không che kín chữ gốc →
   chữ Anh lộ ra + chữ overlay lệch phía trên ⇒ nhân đôi.
2. **Layout sai:** chữ dịch (tiếng Việt dài hơn) không vừa khe block chật của
   mục lục; dấu chấm dẫn + số trang căn phải vỡ.

**Nguyên nhân gốc của ghost:** pipeline hiện tại (L2) giữ NGUYÊN raster có chữ
làm nền và chỉ che hờ bằng scrim. Đây là shortcut, không phải làm sạch.

**Giải pháp (insight của người dùng):** đừng giữ raster có chữ; **dựng lại trang
trên nền sạch.** Phần lớn trang KHÔNG cần AI — chỉ cần ngừng vẽ raster có chữ:
- Trang nội dung (kể cả có ảnh nền trang trí) → nền base-color (trắng/màu nền) +
  chữ dịch. Không có raster chữ bên dưới ⇒ không thể ghost.
- Trang có ảnh minh hoạ → các figure thật đã được cắt sẵn vẫn được ghép lên nền
  sạch.

Chỉ một nhóm nhỏ — bìa/ảnh nghệ thuật full-bleed có chữ đè lên ảnh — mới cần AI
xóa chữ khỏi ảnh (Pha 2). **Pha 1 (tài liệu này) KHÔNG dùng AI.**

## Quyết định đã chốt

- **Bộ phân loại tự quyết** chính sách nền theo loại trang (dùng nhãn #0
  `page_class`/`cover`), không cần người chọn tier.
- Coi "làm sạch trang" là **một chức năng** thống nhất (xử lý nền), tái dùng
  slot-fit L3 cho chữ.

## Chính sách nền (3 giá trị)

`resolve_background_policy(page_class, cover) -> str`:

| Policy | Áp dụng | Hành vi render (Pha 1) |
|---|---|---|
| `base-color` | `text`; và `regenerable` mà `cover == "none"` (trang nội dung có ảnh nền trang trí, vd trang 2) | KHÔNG vẽ raster; nền = `background.color`. Bỏ luôn box scrim per-block (không có gì để che). Vẫn vẽ figures + chữ dịch. |
| `keep-raster` | `preserve` (sơ đồ/biểu đồ/bảng — giữ chính xác) | Vẽ raster gốc + box + chữ như hiện tại (giữ nguyên hành vi). |
| `clean-photo` | `regenerable` mà `cover in (front, back)` (bìa/ảnh nghệ thuật) | **Ý định:** AI xóa chữ giữ ảnh (Pha 2). **Pha 1 fallback:** xử như `keep-raster` (giữ ảnh, ghost còn lại chỉ trên 1–2 trang bìa). |

Bảng ánh xạ:
```
preserve                      -> keep-raster
regenerable + cover front/back -> clean-photo  (Pha1: như keep-raster)
regenerable + cover none       -> base-color
text                          -> base-color
(mặc định an toàn)            -> keep-raster
```

Mặc định an toàn là `keep-raster` để không vô tình bỏ nền của trang chưa rõ.

## Thành phần

### 1. `background_policy.py` (mới, thuần)
`resolve_background_policy(page_class: str, cover: str) -> str` trả về một trong
`{"base-color", "keep-raster", "clean-photo"}` theo bảng trên. Hàm thuần, test
đơn vị được.

### 2. `text_layer_renderer.render_text_layer` (sửa nhỏ)
Hiện tại luôn vẽ `<img class="tl-bg">` khi `background.image` tồn tại, và luôn
thêm `box_css` per-block. Sửa:
- Tính `policy = resolve_background_policy(model.page_class, model.cover)`.
- **Vẽ raster** `<img class="tl-bg">` chỉ khi `policy != "base-color"` và có
  `background.image`. (`clean-photo` Pha 1 vẫn vẽ raster.)
- **Box per-block** (`box_css`) chỉ áp dụng khi `policy != "base-color"`; với
  `base-color` bỏ box (nền sạch, không cần che).
- Figures (`<img class="tl-fig">`) và chữ dịch: vẽ như hiện tại trong MỌI policy
  (figure đã được ghép lên nền sạch sẵn).
- Nền `<div class="tl-page">` vẫn dùng `background.color` như hiện tại — với
  `base-color` đây trở thành nền nhìn thấy duy nhất.

Không đổi chữ ký `render_text_layer`. Không đổi `page_renderer.render_page`.

## Luồng dữ liệu

`PageModel` (đã có `page_class`/`cover` từ #0) → `render_page` →
`render_text_layer` → `resolve_background_policy` quyết định có vẽ raster không →
HTML. Trang 2 (`regenerable`, `cover none`) → `base-color` → nền trắng + 12 block
mục lục, **không còn ghost**.

## Layout mục lục (câu hỏi 2)

Trên nền sạch, ghost biến mất và slot-fit L3 hoạt động thoải mái hơn. **Giữ đúng
cấu trúc TOC** (leader dots + số trang căn phải) là cải tiến RIÊNG, **ngoài phạm
vi Pha 1** — Pha 1 chỉ bảo đảm chữ dịch nằm trên nền sạch, không đè raster.

## Ngoài phạm vi Pha 1

- KHÔNG gọi AI/inpaint (đó là Pha 2 cho `clean-photo`).
- KHÔNG tái dựng cấu trúc TOC (leader dots/số trang).
- KHÔNG đổi extraction, schema DB, hay nhãn #0.
- KHÔNG đổi đường fallback `layout_json`/`render_overlay_html`.

## Kiểm thử (TDD)

- `resolve_background_policy`: 5 ca theo bảng ánh xạ (preserve→keep-raster;
  regenerable+front→clean-photo; regenerable+back→clean-photo;
  regenerable+none→base-color; text→base-color; mặc định lạ→keep-raster).
- `render_text_layer`:
  - Trang `regenerable`+`cover none` có `background.image` → HTML **KHÔNG** chứa
    `class="tl-bg"` (không vẽ raster) và **không** có `box_css` per-block; vẫn
    chứa chữ dịch.
  - Trang `preserve` có `background.image` → HTML **CÓ** `class="tl-bg"` (giữ
    raster) — không hồi quy.
  - Trang `regenerable`+`cover front` → vẫn vẽ raster (Pha 1 fallback).

## Các file đụng tới

- Tạo: `app/services/background_policy.py`.
- Sửa: `app/services/text_layer_renderer.py` (routing nền + bỏ box khi base-color).
- Test: `tests/test_background_policy.py` (mới); bổ sung
  `tests/test_text_layer_renderer.py`.
