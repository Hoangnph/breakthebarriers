# Masked AI Inpaint Cleaning — Thiết kế

Ngày: 2026-06-05
Nhánh: tiếp tục `feat/ai-cover-cleaning` (build trên Pha 2)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

## Bối cảnh & vấn đề

Pha 2 dùng Gemini "sửa cả ảnh" để xóa chữ bìa. Đã verify thật: chữ bị xóa nhưng
Gemini **vẽ lại cả ảnh** → đổi bố cục (cô gái trong ảnh gốc biến đổi). Prompt
tuning (2 lần) không ép giữ nguyên được — đây là bản chất của model image.

**Giải pháp người dùng yêu cầu:** "dùng AI tạo ảnh NHƯNG cài giải pháp inpaint"
— vẫn dùng Gemini sinh phần trám, nhưng **chỉ áp dụng cho vùng có chữ** (mask),
giữ nguyên phần còn lại của ảnh gốc. Mục tiêu: bảo toàn fidelity để người dùng
**đánh giá chất lượng** so với cách "full" hiện tại.

Dữ liệu sẵn có (bìa): raster `page-1.png` 1191×1684 = 2.0× page-points
(595.3×841.9). Text blocks (bbox điểm) là nguồn mask, vd s3 tiêu đề
`[36, 516.8, 432.5, 217]`.

## Nguyên tắc cốt lõi

Gemini vẫn trả về ảnh sạch toàn phần `ai_clean`. Ta **composite theo mask**:
```
result = original * (1 - mask) + resize(ai_clean) * mask
```
`mask` = 1 ở vùng có chữ (mềm hoá biên), 0 ở nơi khác. ⇒ mọi pixel ngoài vùng
chữ **y hệt ảnh gốc**; chỉ vùng chữ lấy từ ảnh AI.

## Quyết định đã chốt

- Kỹ thuật: **AI sinh ảnh + composite theo mask** (không phải cv2.inpaint cổ điển).
- Mask từ **bbox text block + nới biên (dilate) + feather**; không bám nét chữ.
- Giữ CẢ hai method (`full` cũ + `inpaint` mới) để so sánh; mặc định để người
  dùng chọn sau khi xem kết quả thật.

## Thành phần (đều trong `image_cleaner.py`)

### 1. Refactor: `_gemini_clean_bytes(src_path, *, client=None, model=None) -> bytes | None`
Tách phần gọi Gemini hiện có trong `clean_page_background` thành helper trả về
**bytes ảnh AI** (None nếu lỗi/không có ảnh/không key). `clean_page_background`
(full, đang dùng ở Pha 2) viết lại để gọi helper này rồi ghi bytes ra file —
hành vi & test cũ không đổi.

### 2. `build_text_mask(boxes_px, width, height, *, dilate=6, feather=9) -> np.ndarray`
Thuần (numpy/cv2). `boxes_px` = list `(l, t, w, h)` pixel. Vẽ hình chữ nhật trắng
(1.0) cho từng box trên nền đen kích thước `height×width`; `cv2.dilate` nới biên
`dilate` px; `cv2.GaussianBlur` (kernel lẻ từ `feather`) làm mềm. Trả mảng float
`[0,1]` shape `(height, width)`.

### 3. `composite_inpaint(original_bgr, ai_bgr, mask) -> np.ndarray`
Thuần. Resize `ai_bgr` về kích thước `original_bgr`; mở rộng `mask` ra 3 kênh;
`result = original*(1-mask) + ai*mask` (uint8). Trả ảnh BGR.

### 4. `clean_page_background_inpaint(src_path, out_path, boxes_px, *, client=None, model=None) -> bool`
- `ai_bytes = _gemini_clean_bytes(src_path, client=client, model=model)`; None → `False`.
- Decode `ai_bytes` (cv2.imdecode) + đọc `original = cv2.imread(src_path)`.
- `mask = build_text_mask(boxes_px, W, H)` với W,H của original.
- `result = composite_inpaint(original, ai, mask)`; `cv2.imwrite(out_path, result)`; `True`.
- Lỗi bất kỳ → `False` (giữ ảnh gốc).

## Endpoint (`documents.py`)

`POST /api/docs/{id}/pages/{n}/clean-bg` thêm tham số `method=full|inpaint`
(mặc định `full`):
- Tính `boxes_px` từ `pm.blocks`: scale = raster_w / pm.page_w (mở ảnh gốc lấy
  W,H); mỗi block `(l,t,w,h)` điểm → `(l*sx, t*sy, w*sx, h*sy)` pixel.
- `method=full` → `clean_page_background` → `page-N.clean.png` (như Pha 2).
- `method=inpaint` → `clean_page_background_inpaint(..., boxes_px)` →
  `page-N.clean-inpaint.png`.
- Set `pm.background["clean_image"]` = file vừa tạo; cache theo file tồn tại;
  502 nếu thất bại. (Gating `clean-photo`, 400/404 như Pha 2 — không đổi.)

## Frontend

Nút "Làm sạch nền AI" thêm lựa chọn method (Full / Inpaint) — tối thiểu, ví dụ 2
nút con hoặc dropdown. UI đầy đủ ở #3.

## Đánh giá chất lượng

Sau khi code + test xong, **tôi chạy thật cả hai biến thể** trên bìa, gửi bạn so
sánh trực tiếp (Full vs Inpaint). Bạn chọn method mặc định sau khi xem.

## Kiểm thử (TDD, backend, KHÔNG gọi mạng)

- `build_text_mask`: 1 box giữa ảnh → vùng box ≈ 1.0, góc xa = 0.0; có dilate nên
  mask rộng hơn box gốc một chút.
- `composite_inpaint`: original toàn xanh, ai toàn đỏ, mask = 1 trong 1 ô vuông
  giữa → pixel giữa ≈ đỏ (ai), pixel biên ≈ xanh (gốc).
- `clean_page_background_inpaint`: client AI **mock** trả bytes PNG đỏ; original
  PNG xanh trên đĩa tmp; boxes phủ giữa → file ra: giữa đỏ, biên xanh; mock không
  ảnh → `False`.
- `_gemini_clean_bytes`: mock client trả inline image → bytes; không ảnh → None.
- Endpoint `method=inpaint`: cleaner mock → cập nhật `clean_image =
  page-N.clean-inpaint.png`.

## Ngoài phạm vi

- cv2.inpaint cổ điển (người dùng muốn "AI tạo ảnh").
- Mask bám nét chữ (chỉ dùng bbox + dilate).
- UI so sánh side-by-side cầu kỳ (so sánh qua ảnh tôi gửi).
- Chốt method mặc định (người dùng quyết sau khi đánh giá).

## Các file đụng tới

- Sửa: `app/services/image_cleaner.py` (refactor + 3 hàm mới),
  `app/routers/documents.py` (tham số `method` + tính boxes_px).
- Frontend: nút chọn method trong preview (verify thủ công).
- Test: bổ sung `tests/test_image_cleaner.py`, `tests/test_preview_pagemodel.py`.
