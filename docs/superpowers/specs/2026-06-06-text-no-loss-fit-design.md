# 3a — Chữ dịch không mất (role-based fit) — Thiết kế

Ngày: 2026-06-06
Nhánh dự kiến: tiếp tục `feat/manual-per-page`
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

Việc **#3a** (3b = cấu trúc TOC, làm sau).

## Bối cảnh & vấn đề

Khi chữ dịch (tiếng Việt) DÀI hơn bản gốc, người dùng thấy **mất chữ**. Ví dụ
verify thật: tiêu đề trang 3 "LỜI NÓI ĐẦU" chỉ hiện "LỜI NÓI", "ĐẦU" biến mất.

**Nguyên nhân (đã soi):** L3 cho mỗi block giãn xuống "slot" (khoảng trắng dưới)
để tránh chữ li ti — tốt cho đoạn văn. Nhưng với **heading**, slot lớn khiến chữ
KHÔNG co mà **wrap 2 dòng**; dòng 2 tràn xuống ngoài vùng nền thiết kế (banner)
→ chữ trắng rơi trên nền trắng → vô hình. (Bản gốc "FOREWORD" 1 từ không wrap nên
không lỗi.) Div tiêu đề thực tế: `width 30.6%`, `max-height 9.69%` (~82pt ≈ 2
dòng), `font 32.5px`, `color #ffffff`.

## Quyết định đã chốt

- Hướng: **chống clip + co chữ đủ chỗ** (KHÔNG đụng màu/contrast).
- Phân biệt theo `role`: heading co để ở lại ô gốc; body giữ hành vi L3.

## Thiết kế — fit theo vai trò block

Trong `render_text_layer`, hiện mọi block fit theo `slot_h` (khoảng giãn). Đổi:

| role | Fit target (cao) | `max-height` CSS | Hệ quả |
|---|---|---|---|
| **heading** | **bbox `h`** (ô gốc) | **bbox `h`** (clamp đúng vùng gốc) | co font để vừa ~số dòng gốc; ở lại trên banner; không tràn xuống nền khác |
| body/khác | `slot_h` (như L3) | `slot_h` | dùng khoảng trắng, tránh chữ li ti (giữ nguyên) |

Cụ thể trong vòng block:
```python
is_heading = blk.role == "heading"
fit_h = h if is_heading else slot_h          # heading fit vào ô gốc
max_h = h if is_heading else slot_h          # heading clamp = bbox; body = slot
size = fit_font_size(text, w, fit_h, max_size=base, min_size=6.0, height_growth=1.0)
# emit: min-height = pct(h); max-height = pct(max_h)
```
- `min-height` vẫn = bbox `h` (đã có).
- Vòng shrink client co tới khi vừa `clientHeight` (= max-height). Với heading,
  max-height = bbox `h` (nhỏ) → co font để vừa → tiêu đề "LỜI NÓI ĐẦU" co còn 1
  dòng trên banner → đọc được, không mất.
- Body giữ overflow:hidden + slot như L3 (không hồi quy).

**`fit_font_size` không đổi** — chỉ đổi tham số `h` truyền vào (bbox cho heading,
slot cho body).

## Không mất chữ

Heading co vừa ô gốc nên không clip/tràn. Sàn font 6px như cũ; heading thường
ngắn nên hiếm khi chạm sàn. Body vẫn fit theo slot (đã ổn từ L3).

## Kiểm thử (TDD)

- `render_text_layer`: trang có 1 heading + 1 body, slot của heading > bbox của
  heading (có khoảng trắng dưới).
  - Heading div: `max-height` == `min-height` (cùng = pct bbox h) → KHÔNG dùng slot.
  - Body div: `max-height` > `min-height` (slot > bbox) → vẫn dùng slot.
- `render_text_layer`: heading có text dài → `font-size` nhỏ hơn so với khi fit
  theo slot (co để vừa ô gốc). (Assert font-size heading ≤ một ngưỡng / nhỏ hơn
  cùng text fit theo slot.)
- (verify thật) tiêu đề trang 3 hiện đủ "LỜI NÓI ĐẦU" trên banner (1 dòng).

## Ngoài phạm vi

- Màu/contrast/shadow (đã loại).
- Cấu trúc TOC: chấm dẫn, số trang căn phải, chống đè trang mục lục (= 3b).
- Đoạn body quá dài trong ô chật vẫn có thể nhỏ (đánh đổi "co chữ đủ chỗ").

## Các file đụng tới

- Sửa: `app/services/text_layer_renderer.py` (fit target + max-height theo role).
- Test: bổ sung `tests/test_text_layer_renderer.py`.
