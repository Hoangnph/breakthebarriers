# Raster-always + Masking (Sub-project B2.1) — Thiết kế

Ngày: 2026-06-09
Nhánh: `fix/layout-original-to-html`
Trạng thái: đã duyệt thiết kế

PDF kiểm chứng: `apps/break_the_barriers/assets/books/2024-wttc-introduction-to-ai.pdf`.

## Bối cảnh

Theo kiến trúc faithfulness-first (raster-truth + overlay), renderer per-page `text_layer_renderer.render_text_layer` đã: vẽ raster + đặt figure + overlay text dịch + fit chữ. NHƯNG còn hai khiếm khuyết khiến trang `text` mất nội dung:

1. **Trang `text`/`regenerable` bỏ raster.** `resolve_background_policy`: `text → base-color`, `regenerable → base-color`; `render_text_layer` đặt `draw_raster = policy != "base-color"` → **không vẽ raster** cho các trang này. Hơn nữa `background.image` bị null cho trang `text` (extractor). ⇒ bảng/đồ hoạ trên trang text biến mất (vd p38 bảng ANNEX, p29 sơ đồ) — đúng các lỗi đã báo.
2. **Mask quá mờ.** Khi có overlay, `Block.box` cho trang trắng là `scrim rgba(255,255,255,0.55)` (chỉ 55% đục) → chữ gốc lộ qua (ghost). Và mask chỉ áp khi `policy == "keep-raster"` → trang text không được mask.

Bằng chứng: render `render_page` cho p12 (mixed) → `tl-bg=True`, 14 overlay (faithful+dịch OK); p38/p29 (text) → `tl-bg=False` (mất đồ hoạ). `Block.box` có sẵn cho mọi trang.

Mục tiêu B2.1: `text_layer_renderer` **luôn vẽ raster cho mọi trang + che chữ gốc đủ đậm** → reader/sidebar/split chế độ Dịch trở nên trung thực + dịch cho MỌI trang. (Flow liền mạch là B2.2.)

## Thiết kế

### A. Luôn vẽ raster (`render_text_layer`)
- Nguồn ảnh nền, thứ tự ưu tiên:
  1. `background.clean_image` nếu `policy == "clean-photo"` (giữ hành vi cover hiện tại).
  2. `background.image`.
  3. **Fallback `page-{model.page_num}.png`** khi hai cái trên None (raster luôn tồn tại trên đĩa; `background.image` bị null cho trang text).
- **Bỏ cổng `draw_raster`/`base-color`**: luôn `<img class="tl-bg">` khi có tên ảnh. Giữ `bg` màu nền (mặc định trắng) để hiện khi ảnh 404.
- Yêu cầu: `model.page_num` phải được set (xem mục C).

### B. Masking đủ đậm (`render_text_layer` + helper thuần)
- Áp **mask cho MỌI block có overlay** khi raster được vẽ (bỏ điều kiện `policy == "keep-raster"`).
- Helper thuần `_mask_css(box) -> str`:
  - Rỗng nếu `box`/`box.fill` không có.
  - `_opaque_fill(fill, min_alpha=0.9)`: nếu `fill` là `rgba(r,g,b,a)` với `a<0.9` → nâng `a=0.9` (giấu chữ gốc); nếu hex/màu đặc → giữ nguyên (đã đục).
  - `scrim` → thêm `padding:0 2px;`. Trả `background:{opaque_fill};{pad}`.
- Mask phủ đúng bbox block (đã có), nay đục ~0.9 → chữ gốc bị che, text dịch nằm trên. Mặt đánh đổi: text trên ảnh/photo có thể thấy hộp màu nền cục bộ — chấp nhận (đa số block nằm trên nền gần đặc; tinh chỉnh/inpaint là việc sau).

### C. Endpoint set `page_num` (`documents.py` `get_page_content`)
- Sau `pm = PageModel.from_json(page.model_json)` thêm `pm.page_num = page_num` trước `render_page` (giống flow endpoint), để fallback raster ở mục A hoạt động.

### Không đổi
- `compute_slot_heights`, `fit_font_size`, slot-growth, TOC entry, zoom/edit script — giữ nguyên.
- Extraction, `Block.box` (analyze_block_box) — giữ nguyên (mask data đã đủ).

## Đơn vị

| Unit | Vai trò | Test |
|------|---------|------|
| `_opaque_fill(fill, min_alpha)` | nâng alpha rgba để che chữ | unit |
| `_mask_css(box)` | sinh CSS mask từ box | unit |
| `render_text_layer` (raster-always + mask-always) | render trang faithful+dịch | integration (model giả) |
| `get_page_content` set page_num | bật fallback raster | integration (endpoint) |

## Kiểm thử & kiểm chứng

- **Unit:** `_opaque_fill('rgba(255,255,255,0.55)') == 'rgba(255,255,255,0.9)'`; hex passthrough; `_mask_css` ra `background:`; rỗng khi không box.
- **Integration (render_text_layer):** model trang `text` (page_class=text, `background.image=None`, page_num=38, 1 block + box scrim) + translations → HTML chứa `<img class="tl-bg"` trỏ `page-38.png` **và** block có `background:rgba(255,255,255,0.9)`.
- **Integration (endpoint):** `GET /pages/38?lang=vi&raw=true` (seed DBPage model_json text + translation) → 200, chứa `page-38.png`.
- **Kiểm chứng thủ công:** mở reader chế độ Dịch trên doc mẫu các trang p38/p29 (bảng/đồ hoạ hiện trở lại, chữ dịch không bị ghost) và p12/p34 (không hồi quy).

## Ngoài phạm vi
- **B2.2:** flow liền mạch (chuỗi fragment faithful+overlay).
- Inpaint AI xoá chữ gốc (mask hiện dùng hộp màu — đủ cho phần lớn trang).
- Thay đổi UI mode (B3): ẩn/bỏ mode `HTML(en)` reflow.

## Rủi ro & giảm thiểu
- **Ghost còn sót / hộp mask xấu trên ảnh** → mask đục 0.9 che phần lớn; trang phức tạp tinh chỉnh sau (có thể inpaint ở B-sau). Không chặn B2.1.
- **Hồi quy trang mixed đang tốt (p12)** → mixed vốn đã vẽ raster + mask keep-raster; thay đổi chỉ NỚI thêm cho text page và nâng alpha → kiểm chứng p12/p34 không đổi xấu.
- **`page_num` không set ở nơi gọi khác** → fallback chỉ kích hoạt khi `page_num>0`; nếu 0 thì bỏ qua (an toàn, không trỏ `page-0.png`).
