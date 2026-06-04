# Pha 2 — AI Cover Cleaning + 3 trạng thái xem — Thiết kế

Ngày: 2026-06-04
Nhánh dự kiến: nhánh mới tách từ `main` (vd `feat/ai-cover-cleaning`)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

## Bối cảnh

Sau Clean-Page Pha 1, trang nội dung đã hết ghost (bỏ raster, dùng nền sạch).
Nhưng trang `clean-photo` (bìa/ảnh full-bleed có chữ nung) Pha 1 vẫn giữ raster
→ **bìa còn ghost**. Pha 2 dùng AI xóa chữ khỏi ảnh để bìa sạch. Đồng thời thêm
**3 trạng thái xem** để người dùng đối chiếu nguồn ↔ tái dựng ↔ bản dịch.

Hiện trạng liên quan:
- `google-genai 2.6.0` đã cài; `GEMINI_API_KEY` hoạt động (translator dùng).
- Ảnh phục vụ qua `GET /api/docs/{id}/assets/{filename}` từ thư mục extracted.
- `GET /api/docs/{id}/pages/{n}` nhận `lang=en|vi`, render qua `render_page`;
  `raw=true` trả HTML (inject page_size), non-raw trả JSON `{..., html, page_class, cover}`.
- `resolve_background_policy(page_class, cover)` → base-color/keep-raster/clean-photo;
  `render_text_layer` chỉ vẽ raster + box khi `policy != base-color`.

## Quyết định đã chốt

- AI làm sạch **theo yêu cầu (nút bấm) + cache**, không tự động.
- Cách xóa chữ: **Gemini sửa cả ảnh bằng prompt** (image-edit).
- Pha 2 chỉ **nút tối thiểu**; UI đầy đủ ở #3.
- "Bản gốc" = **raster trang đã trích** (`page-N.png`), không nhúng PDF.
- **KHÔNG ghi đè `background.image`**; ảnh sạch lưu field riêng `background.clean_image`
  (để view `original` luôn lấy được ảnh gốc nguyên vẹn).

---

## Thành phần A — AI Cover Cleaning

### A1. `image_cleaner.py` (mới, service)
```
clean_page_background(src_path: str, out_path: str, *, client=None,
                      model: str = <GEMINI_IMAGE_MODEL>) -> bool
```
- Đọc ảnh `src_path`, gọi Gemini image-edit qua
  `client.models.generate_content(model=model, contents=[PROMPT, image])` với
  prompt yêu cầu **xóa mọi chữ/ký tự, giữ nguyên ảnh + bố cục + màu**.
- Trích phần ảnh trả về (inline image data) trong response, ghi ra `out_path`.
  Không có ảnh trong response → trả `False`.
- `client` **tiêm được** (mặc định tạo `genai.Client(api_key=...)`); test truyền
  client mock để không gọi mạng.
- Model lấy từ env `GEMINI_IMAGE_MODEL` (mặc định `gemini-2.5-flash-image`), để
  dễ đổi khi key có/không có quyền. Mọi lỗi (API, quyền, parse) → `False`.

### A2. Endpoint `POST /api/docs/{id}/pages/{n}/clean-bg`
- Nạp trang + `PageModel` từ `model_json`. Tính
  `policy = resolve_background_policy(pm.page_class, pm.cover)`; nếu
  `policy != "clean-photo"` → **400** (chỉ làm sạch trang bìa/ảnh full-bleed).
- File đích `page-{n}.clean.png` trong thư mục extracted. Đã tồn tại và không
  `?force=true` → trả luôn (cache hit).
- Gọi `clean_page_background(page-{n}.png → page-{n}.clean.png)`.
  - Thành công → set `pm.background["clean_image"] = "page-{n}.clean.png"`, lưu
    lại `DBPage.model_json = pm.to_json()`, trả `200 {status:"cleaned", clean_image}`.
  - Thất bại → **502 {status:"failed"}**, không đổi gì (giữ raster gốc).
- `background.image` (raster gốc) **không bị đổi**.

### A3. Renderer dùng ảnh sạch
`render_text_layer`: khi vẽ raster, chọn nguồn theo policy:
- `clean-photo` và có `background.clean_image` → vẽ `clean_image` (ảnh sạch).
- ngược lại (`keep-raster`, hoặc clean-photo chưa làm sạch) → vẽ `background.image`.
Chữ ký hàm không đổi; chỉ đổi tên file ảnh nền được chọn.

---

## Thành phần B — 3 trạng thái xem

### B1. Tham số `view` cho `GET /api/docs/{id}/pages/{n}`
Thêm `view=original|html|translated` (mặc định suy từ `lang` cũ để tương thích
ngược: thiếu `view` thì `lang=en`→`html`, `lang=vi`→`translated`).

| view | Nội dung | Render |
|---|---|---|
| `original` | Trang raster gốc nguyên vẹn (chữ nung, không tái dựng) | HTML chỉ chứa `<img>` full-bleed trỏ `assets/{background.image}`; nếu trang không có raster (`kind=text`, image=None) → fallback `html` |
| `html` | Tái dựng nền sạch, ngôn ngữ gốc | `render_page` với `original_text` (= `lang=en` hiện tại) |
| `translated` | Tái dựng nền sạch, ngôn ngữ đích | `render_page` với `translated_text` (= `lang=vi` hiện tại) |

- `original` giữ đúng hợp đồng `raw=true` (inject page_size) và non-raw (JSON dict
  có thêm `view`, `page_class`, `cover`).
- `html`/`translated` đi đúng đường `render_page` hiện tại (gồm nền AI-cleaned nếu
  có, theo A3).

### B2. Frontend (Next.js) — toggle tối thiểu
Thay toggle 2 nút Original/Translated bằng **3 nút: Gốc / HTML / Dịch** gọi
`view=original|html|translated`. Nút **"Làm sạch nền AI"** chỉ hiện khi
`page_class/cover` ⇒ `clean-photo`; bấm → `POST .../clean-bg` → reload view hiện
tại. UI tối thiểu; bản đầy đủ (revert, trạng thái, hàng loạt) ở #3.

---

## Luồng dữ liệu

Bấm "Làm sạch nền AI" → `POST clean-bg` → `image_cleaner` (Gemini) →
`page-N.clean.png` + cập nhật `model_json.background.clean_image` → reload
`view=translated` → `render_page` vẽ ảnh sạch + chữ dịch → **bìa hết ghost**.
View `original` luôn trả raster gốc để đối chiếu.

## Xử lý lỗi & chi phí

- Chỉ gọi AI khi bấm + cache theo file ⇒ chi phí tối thiểu.
- API/quyền lỗi → `image_cleaner` trả `False` → endpoint 502 → giữ raster gốc
  (đúng hành vi Pha 1, không vỡ trang).
- Giữ `background.image` gốc ⇒ revert = bỏ `clean_image` (để #3 làm UI revert).

## Kiểm thử (TDD, backend)

- `image_cleaner.clean_page_background`: client **mock** trả response có inline
  image bytes giả → ghi đúng `out_path`, trả `True`; response không có ảnh →
  `False`; client ném lỗi → `False` (không vỡ).
- Endpoint `clean-bg`: cleaner mock → cập nhật `model_json.background.clean_image`,
  trả 200; trang không phải `clean-photo` → 400; cache hit (file tồn tại) → không
  gọi lại cleaner.
- `render_text_layer`: trang `clean-photo` có `background.clean_image` → HTML vẽ
  ảnh sạch (chứa tên file clean) chứ không phải ảnh gốc; `clean-photo` chưa sạch →
  vẫn vẽ ảnh gốc.
- `GET pages` `view=original` → HTML chứa `<img>` raster gốc, KHÔNG có `tl-text`;
  `view=html`/`translated` → đi `render_page` (giữ test cũ); tương thích `lang`.

## Ngoài phạm vi Pha 2

- UI đầy đủ manual (revert/regenerate/hàng loạt) = #3.
- Tái dựng cấu trúc TOC (leader dots/số trang).
- Nhúng PDF thật cho "Bản gốc" (enhancement sau).
- Không đổi schema DB (đi kèm `model_json`); không đổi extraction.

## Các file đụng tới

- Tạo: `app/services/image_cleaner.py`.
- Sửa: `app/routers/documents.py` (endpoint clean-bg + tham số `view`),
  `app/services/text_layer_renderer.py` (chọn `clean_image` cho clean-photo).
- Frontend: component preview Next.js (toggle 3 nút + nút làm sạch) —
  `apps/break_the_barriers/frontend` (verify thủ công).
- Test: `tests/test_image_cleaner.py` (mới), bổ sung
  `tests/test_text_layer_renderer.py`, `tests/test_preview_pagemodel.py`.
