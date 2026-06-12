# Raster-Page Render (L2) — local fill / scrim + real fonts, unified renderer

**Ngày:** 2026-06-03
**App:** `apps/break_the_barriers`
**Tiền đề:** Tiếp nối SP-A + L1. Đây là SP-A.2 (L2).
**Trạng thái:** Design — chờ duyệt trước khi lập plan.

---

## 1. Bối cảnh & vấn đề

Sau L1, nội dung được trích đầy đủ và sạch nhiễu. Nhưng trang `image`/`mixed` (bìa, mục-lục-trên-ảnh) vẫn render bằng `render_overlay_html` với **hộp màu đặc** + heuristic `_fit_font_size` thô:
- Chữ dịch tràn khỏi hộp (overflow) → **che nội dung** lân cận (vd "MỤC LỤC" quá to đè leader dots).
- Hộp một màu trên nền photo → mảng vá.
- Không dùng font thật (weight/color/align) dù model (sau L1) đã có.

`render_overlay_html` nhận `layout` dict mất thông tin font; `page_renderer` lại đưa image/mixed qua đúng đường này.

## 2. Mục tiêu & phi-mục tiêu

**Mục tiêu (L2):**
- Trang image/mixed: đặt chữ dịch bằng **font thật từ model** (size/weight/italic/color/align) + **TextFitter** (chống tràn).
- Nền chữ theo từng block: nền đồng nhất → **fill 1 màu cục bộ** (liền panel); nền photo → **scrim bán trong suốt** (đọc rõ, không vá cứng).
- **Gộp renderer:** một renderer PageModel duy nhất cho mọi kind (loại bỏ trùng lặp với `render_text_layer`).

**Phi-mục tiêu:**
- Inpaint/xóa chữ gốc bằng thuật toán ảnh (đã chọn fill/scrim thay thế).
- Thay đổi pipeline trích xuất/dịch (L1 lo việc đó).

**Tiêu chí thành công:**
- Trang 2 WTTC: không còn hộp trắng to đè; "MỤC LỤC" fit gọn trong vùng; mục lục dịch không tràn; chữ trên photo có scrim đọc rõ.
- Trang `text` render **không đổi** (không raster, không box) — test SP-A vẫn xanh.

## 3. Quyết định kiến trúc: gộp renderer (bỏ phần thừa)

Một `render_overlay_v2` riêng sẽ trùng ~80% với `render_text_layer` (cùng đặt block theo bbox%, áp font model, TextFitter, script scale/zoom). → **Tổng quát hóa `render_text_layer`** thành renderer PageModel duy nhất:
- `background.image` != null → nền raster `<img class="tl-bg">`; null → nền màu `background.color` (hành vi text hiện tại).
- mỗi block dịch: div tuyệt đối theo bbox%, font thật + TextFitter; nếu block có `box` → áp nền (fill đặc hoặc scrim rgba).
- figures (ảnh cắt) như hiện tại.

`page_renderer.render_page` đưa **mọi** model-kind qua renderer này. `render_overlay_html` cũ chỉ còn cho đường fallback `layout_json` (tài liệu chưa có model_json) trong endpoint.

```
Extraction (có raster):
  mỗi block → BlockBoxAnalyzer → box={mode:"fill"|"scrim", fill:"#rrggbb"} → model.Block.box
        │
Render:
  page_renderer.render_page(model) → render_text_layer(model) [hợp nhất]
     bg: image? raster : color
     block: bbox% + font thật + TextFitter + box(fill/scrim)
     figures: ảnh cắt
```

## 4. Thành phần

### 4.1 PageModel.Block.box — `app/services/page_model.py`
- Thêm field optional `box: Optional[dict] = None`, dạng `{"mode": "fill"|"scrim", "fill": "#rrggbb"}`.
- `to_dict/from_dict` xử lý field mới (default None → tương thích model cũ).

### 4.2 BlockBoxAnalyzer — `app/services/page_image.py`
- Hàm `analyze_block_box(image_path, bbox_pt, scale_x, scale_y, *, var_threshold=...) -> dict`.
- Lấy mẫu vùng raster phủ bbox: tính độ biến thiên (variance/độ lệch màu) và độ sáng trung bình.
  - Variance thấp (nền đồng nhất, vd panel) → `{"mode":"fill","fill": median_color}`.
  - Variance cao (photo) → `{"mode":"scrim","fill": rgba}` với scrim tối (nền sáng) hoặc sáng (nền tối) theo luminance trung bình, để tương phản chữ.
- **Degrade:** lỗi → `{"mode":"fill","fill": sample_bg_color(...)}` (hành vi hiện tại).
- Tái dùng/đặt cạnh `sample_bg_color`, `is_photo_background` (cùng kiểu lấy mẫu).

### 4.3 Extractor wiring — `app/services/extractor.py`
- Trong vòng lặp trang (nơi đã có raster + blocks), với mỗi block tính `box = analyze_block_box(...)` và gắn vào `Block.box` của model.
- **Degrade:** không có raster → `box=None`.

### 4.4 render_text_layer (tổng quát hóa) — `app/services/text_layer_renderer.py`
- Thêm nhánh nền: nếu `model.background.image` → chèn `<img class="tl-bg" src="{base}/{image}">` (giống `ov-bg` cũ, phủ canvas); else giữ nền màu hiện tại.
- Mỗi block: nếu `block.box`:
  - `mode=="fill"` → `background:{fill}` (đặc).
  - `mode=="scrim"` → `background:{rgba}` + padding nhỏ (scrim ôm chữ).
  - không box → như hiện tại (text-layer trang chữ).
- Giữ nguyên: font stack, TextFitter, script scale/zoom/fit, figures.

### 4.5 page_renderer — `app/services/page_renderer.py`
- `render_page(model, translations, image_url_base)`: mọi model-kind → `render_text_layer(model, ...)`. Bỏ nhánh gọi `render_overlay_html` cho image/mixed.
- `render_overlay_html` giữ nguyên (endpoint vẫn dùng cho fallback `layout_json` khi không có model_json).

## 5. Luồng dữ liệu
PDF → (L1) blocks + fonts → BlockBoxAnalyzer gắn `box` → model.json → translate (L1) → render_page → render_text_layer (nền raster/màu + block font+fit+box + figures).

## 6. Xử lý lỗi / degrade

| Tình huống | Hành vi |
|---|---|
| BlockBoxAnalyzer lỗi | `box={mode:fill, fill:sample_bg_color}` |
| Block thiếu font | default role-based (đã có ở render_text_layer) |
| Block thiếu `box` (model cũ) | nếu có raster nền → fill `background.color`; trang text → như cũ |
| Không raster | `box=None`, nền màu |

## 7. Testing
- **Unit:** `analyze_block_box` (ảnh giả đồng nhất → fill + màu đúng; ảnh gradient → scrim + rgba + chọn tối/sáng đúng theo luminance). PageModel.Block.box roundtrip. `render_text_layer`: có `tl-bg` khi background.image; block fill → `background:#...`; block scrim → có `rgba(`; áp `font-weight/color/text-align`; vẫn có script fit; trang text (image=None, box=None) render **y như trước** (regression). `page_renderer`: image/mixed/text đều ra markup `tl-page` (hợp nhất); legacy `render_overlay_html` không bị xoá.
- **Integration:** re-extract WTTC → model block trang 2 có `box`; render trang 2 → có `tl-bg`, không hộp trắng full đè, có scrim cho block trên photo.

## 8. Phạm vi
- L2 một spec/plan độc lập. Cần **re-extract** để có `box` (trùng re-extract L1).
- Sau L2, đường render image/mixed dùng renderer hợp nhất; `render_overlay_html` chỉ phục vụ fallback layout_json.

## 9. Câu hỏi mở (chốt ở plan)
- Ngưỡng variance phân biệt fill↔scrim; độ đậm scrim (alpha) theo luminance.
- Padding của scrim quanh chữ.
- Có giữ `_model_to_overlay_layout` trong page_renderer không (chỉ cần nếu vẫn còn nhánh overlay_html — sau L2 thì không, nên xoá nếu không còn dùng).
