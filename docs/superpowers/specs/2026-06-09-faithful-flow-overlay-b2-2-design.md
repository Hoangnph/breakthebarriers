# Faithful Flow + Overlay (Sub-project B2.2) — Thiết kế

Ngày: 2026-06-09
Nhánh: `fix/layout-original-to-html`
Trạng thái: đã duyệt thiết kế

PDF kiểm chứng: `apps/break_the_barriers/assets/books/2024-wttc-introduction-to-ai.pdf`.

## Bối cảnh

Sau B1, view `/flow` là chuỗi raster gốc (không dịch) → trùng "Gốc", vô nghĩa với app dịch. Sau B2.1, renderer per-page `text_layer_renderer` đã faithful + overlay dịch cho mọi trang (luôn vẽ raster + mask chữ gốc), nhưng chỉ phục vụ reader/sidebar/split (px tuyệt đối + scale-to-fit bằng JS — hợp cho 1 trang đầy màn hình).

B2.2 đưa năng lực faithful+overlay đó vào **flow liền mạch**: một tài liệu cuộn dọc gồm nhiều **fragment 1 trang**, mỗi fragment co theo bề rộng cột bằng **cqw** (container query width). Frontend không đổi (vẫn 1 iframe `/flow`).

**Nguyên tắc:** tạo renderer fragment **mới** dùng cqw, **không refactor lõi** `render_text_layer` (vừa ổn định ở B2.1); chỉ **trích** phần quyết định raster/mask thành 1 helper thuần dùng chung để hai đường luôn nhất quán.

## Thiết kế

### A. Helper dùng chung (trích từ `text_layer_renderer`)
`resolve_page_raster(model) -> tuple[str | None, bool, bool]` → `(image_name, mask_original, force_white)`:
- `policy_override == "base-color"` → `(None, False, True)` (escape hatch: bỏ raster, nền trắng).
- `policy == "clean-photo"` và có `clean_image` → `(clean_image, False, False)` (chữ đã xoá, không mask).
- else → `image_name = background.image or page-{page_num}.png`; `(image_name, image_name is not None, False)`.

`render_text_layer` được sửa để gọi helper này (thay đoạn logic inline tương đương) — hành vi không đổi, các test B2.1 vẫn xanh. Helper đặt trong `text_layer_renderer.py` (cạnh `_mask_css`).

### B. Fragment thuần `render_faithful_page(model, translations, image_url_base) -> str`
(đặt trong `faithful_flow_renderer.py`). Trả về MỘT khối trang (không phải tài liệu đầy đủ):

- `<section class="ff-page" style="aspect-ratio:{pw}/{ph}">` — CSS đặt `container-type: inline-size; position: relative`.
- **Nền:** từ `resolve_page_raster`. Nếu có `image_name` → `<img class="ff-bg" src=".../{image_name}">` (position absolute, inset 0, width/height 100%). `force_white` → không ảnh (nền trắng từ CSS `.ff-page`).
- **Figures:** `<img class="ff-fig" style="left/top/width/height %">` (tái dùng `_pct`).
- **Text dịch:** với mỗi block có translation:
  - vị trí `left/top/width` theo % trang; `min-height/max-height` % theo slot (tái dùng `compute_slot_heights`, single-line clamp như text_layer).
  - cỡ chữ: tính `size_px = fit_font_size(...)` (như text_layer) rồi **`font-size: {cqw}cqw` với `cqw = size_px / pw * 100`** (1cqw = 1% bề rộng trang → chữ co đúng tỉ lệ ở mọi bề rộng). Lưu `data-cqw="{cqw}"` để script fit tinh chỉnh.
  - mask: `_mask_css(blk.box)` khi `mask_original`.
  - font-family/weight/italic/color/align như text_layer; TOC entry (`parse_toc_entry`) giữ.

### C. Doc assembler `render_faithful_flow(pages, translations, image_url_base) -> str`
(thay hàm raster-only của B1 trong `faithful_flow_renderer.py`):
- `pages`: List[PageModel] (đã set `page_num`). `translations`: dict `span_id -> text` gộp theo trang? → KHÔNG: dùng key theo trang. **Quyết định:** translations là dict `{page_num: {span_id: text}}` để mỗi fragment lấy đúng map trang mình. (Đơn giản, tránh va span_id giữa trang.)
- Ghép: `<article class="ff-doc">` chứa N `render_faithful_page(...)`; nạp 1 lần fonts + CSS + script.
- **Script fit cqw (1 lần/khi resize, debounce):** mỗi `.ff-text`: đặt `fontSize = dataset.cqw + 'cqw'`; nếu `scrollHeight > clientHeight+1` → giảm cqw dần (−0.2, tối đa ~40 vòng, sàn ~1cqw) tới khi vừa. (Vì trang co đồng đều, fit 1 lần đúng cho mọi bề rộng; vẫn nghe resize để chắc.) Nhận `btb-zoom` → đổi `--ff-zoom`/max-width cột rồi fit lại.
- Trả tài liệu HTML đầy đủ (DOCTYPE…).

### D. Endpoint `/api/docs/{id}/flow` (`documents.py`)
- Nạp `page_rows` (order page_num); với mỗi trang có `model_json` → `PageModel.from_json`, set `page_num`.
- Nạp `DBTranslation` của doc; build `translations = {page_num: {span_id: (translated_text|original_text theo lang)}}`.
- `image_base` như cũ; trả `render_faithful_flow(pages, translations, image_base)`.
- Giữ chữ ký + `HTMLResponse` → frontend không đổi.

## Tái dùng / không đổi
- `_mask_css`, `_opaque_fill`, `compute_slot_heights`, `fit_font_size`, `_FONT_STACK`, `_GOOGLE_FONTS`, `parse_toc_entry`, `effective_policy` — import lại.
- `render_text_layer` (per-page) chỉ đổi để gọi `resolve_page_raster` (hành vi giữ nguyên).
- Frontend `LayoutFlow` / preview — không đổi.

## Đơn vị

| Unit | Vai trò | Test |
|------|---------|------|
| `resolve_page_raster(model)` | quyết định raster/mask/white | unit |
| `render_faithful_page(model, trans, base)` | fragment 1 trang (cqw) | unit |
| `render_faithful_flow(pages, trans, base)` | ghép doc + script fit | unit + integration |
| `/flow` endpoint | nạp models+translations → render | integration |

## Kiểm thử & kiểm chứng

- **Unit `resolve_page_raster`:** text page (image None, page_num=5) → `(page-5.png, True, False)`; override base-color → `(None, False, True)`; clean-photo+clean_image → `(clean, False, False)`. `render_text_layer` vẫn xanh (B2.1 tests).
- **Unit `render_faithful_page`:** trang text page_num=38 + 1 block translation → fragment chứa `ff-page` với `aspect-ratio:595/842`, `<img class="ff-bg" ...page-38.png`, text div có `cqw` + `data-cqw` + mask `rgba(255,255,255,0.9)`; block không có translation → không emit text div.
- **Unit `render_faithful_flow`:** 2 PageModel + translations theo trang → 2 `ff-page`, đúng thứ tự, có script `btb-zoom` + fit; trang không dịch → chỉ raster.
- **Integration `/flow`:** seed doc 2 trang (model_json text + translations) → 200, chứa `page-1.png`, `page-2.png`, `ff-page`, text dịch.
- **Kiểm chứng thủ công:** mở `/flow` doc WTTC (lang=vi) → cuộn 44 trang: faithful (bảng/đồ hoạ/thiết kế) + text dịch overlay không chồng; p38/p29/TOC đúng.

## Ngoài phạm vi (B3)
- Dọn UI mode: ẩn/bỏ `HTML(en)` reflow; NAV/TOC từ TOC gốc; tinh chỉnh mask trên ảnh phức tạp (inpaint).

## Rủi ro & giảm thiểu
- **Tràn chữ dịch** → server-side `fit_font_size` + script fit cqw + `overflow:hidden` clamp. Tràn hiếm bị giảm cỡ, không chồng.
- **Đổi chữ ký `render_faithful_flow`** (B1 dùng page_nums) → cập nhật `tests/test_faithful_flow.py` sang hợp đồng mới (models+translations); B2.2 thay flow raster-only của B1.
- **44 ảnh nặng** → `loading="lazy"` trên `ff-bg`.
- **cqw hỗ trợ trình duyệt** → cqw (container query units) đã phổ biến ở trình duyệt hiện đại; iframe preview dùng Chromium/WebKit hiện hành → OK.
