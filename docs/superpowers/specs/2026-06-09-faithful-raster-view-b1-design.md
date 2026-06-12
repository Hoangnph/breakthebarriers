# Faithful Raster View (Sub-project B1) — Thiết kế

Ngày: 2026-06-09
Nhánh: `fix/layout-original-to-html`
Trạng thái: đã duyệt thiết kế

PDF kiểm chứng: `apps/break_the_barriers/assets/books/2024-wttc-introduction-to-ai.pdf`
Doc mẫu đã extract: `data/extracted_html/2024-wttc-introduction-to-ai/` (44 trang, có `page-{n}.png` 1191×1684 cho mọi trang).

## Bối cảnh & nguyên nhân gốc

View mặc định `/api/docs/{id}/flow` hiện **tái dựng (reflow)** mỗi trang từ text-block docling + figure nhận diện được. Cách này mất mát theo thiết kế: trên `2024-wttc-introduction-to-ai.pdf` phát sinh **17 lỗi render** (mất bảng, mất ảnh vector, mất nền/cấu trúc trang thiết kế, vỡ đa cột, box đen banner, mất format chữ). Chi tiết root-cause: xem memory `flow-reconstruction-lossy` và phần dưới.

Bằng chứng then chốt:
- **Raster cả trang `page-{n}.png` tồn tại cho MỌI trang** (extractor `save_page_image` chạy mỗi trang; docling `images_scale=2.0`). Raster chứa sẵn toàn bộ: bảng, đồ hoạ vector, thiết kế, đa cột, banner.
- Nhưng `extractor.py` đặt `background.image = image_name if kind != "text" else None` → raster bị **null hoá** cho trang `text`, nên các renderer bỏ qua nó → đồ hoạ biến mất.
- Bảng chỉ là `Block(role="table", text="")` (không có cấu trúc ô); `flow_renderer` không có nhánh table → đổ thành `<p>` rỗng.

**Quyết định kiến trúc (đã duyệt):** faithfulness-first, raster-truth. View faithful của tài liệu = **chuỗi dọc các ảnh raster gốc**. Vì raster là chính bản gốc, mọi nội dung được giữ trung thực 100% cho bất kỳ tài liệu nào, không cần tái dựng từng loại nội dung.

## Phạm vi

**B1 (tài liệu này):** view faithful = chuỗi raster. Backend nhỏ, không đổi model/extractor, không đổi frontend.

**Ngoài phạm vi B1** (sub-project sau, spec riêng):
- **B2:** overlay text dịch lên raster (inpaint chữ gốc + fit không chồng — làm chắc bug L3).
- **B3:** NAV sinh từ TOC gốc; dọn banner black-box; polish.
- Tăng `images_scale` (nét hơn) — tuỳ chọn, cần extract lại; KHÔNG làm trong B1.

## Thiết kế

### A. Renderer thuần `faithful_flow_renderer.py` (mới)

```
render_faithful_flow(page_nums: List[int], image_url_base: str) -> str
```

- Trả về **1 tài liệu HTML cuộn dọc**: với mỗi `n` trong `page_nums` (đã sort tăng dần), emit
  `<figure id="pg-{n}" class="fr-page"><img class="fr-img" src="{image_url_base}/page-{n}.png" alt="Trang {n}" loading="lazy"/></figure>`.
- Thuần: chỉ nhận list số trang + base URL, không I/O, không DB → unit-test trực tiếp.
- CSS: nền `#f4f4f5`; cột giữa `max-width` ~900px; `.fr-img { width:100%; height:auto; display:block; box-shadow:0 2px 14px rgba(0,0,0,.25); margin:0 0 16px; border-radius:2px; }`. `loading="lazy"` để 44 ảnh không tải cùng lúc.
- **Zoom script** (giữ tương thích nút zoom frontend): nghe `message` `btb-zoom` → đặt `--fr-zoom` và scale chiều rộng cột (`document.querySelector('.fr-doc').style.maxWidth = (900*zoom)+'px'`). Cùng giao thức `postMessage({type:'btb-zoom',zoom})` như flow cũ.
- Escape an toàn `image_url_base` và số trang (số nguyên).

### B. Endpoint `/api/docs/{id}/flow` (sửa `documents.py`)

- Giữ chữ ký + hợp đồng iframe hiện tại (`lang`, trả `HTMLResponse`) → **frontend không phải đổi** (vẫn iframe `/flow?lang=...`).
- Lấy danh sách trang: `page_nums = [r.page_num for r in page_rows]` (đã `order_by(page_num)`), lọc các trang có raster trên đĩa (`page-{n}.png` tồn tại) để không emit ảnh hỏng.
- `image_base` giữ nguyên (`{base_url}/api/docs/{doc_id}/assets`). Asset endpoint đã serve `page-{n}.png` từ `extracted_html/{doc_id}/`.
- Trả `render_faithful_flow(page_nums, image_base)`.
- **Tham số `lang`:** vẫn nhận để giữ hợp đồng, nhưng B1 luôn trả raster gốc cho cả `en|vi` (overlay dịch là B2). Ghi chú rõ trong code: view "Dịch" tạm hiển thị raster gốc cho tới khi B2 thay — đánh đổi có chủ đích (ưu tiên faithfulness, giao hàng tăng dần).
- `build_document_flow`/`flow_renderer` reflow **không xoá** (còn dùng cho fallback/tham chiếu), chỉ thôi gọi từ endpoint flow.

### C. Asset raster
- Không đổi. `GET /api/docs/{id}/assets/{filename}` đã phục vụ `page-{n}.png` từ `extracted_html/` (fallback `pages/`). Raster đã có sẵn cho doc mẫu; doc mới được `save_page_image` ghi khi extract.

## Đơn vị (isolation)

| Unit | Vai trò | Phụ thuộc | Test |
|------|---------|-----------|------|
| `render_faithful_flow` | sinh HTML chuỗi raster | thuần | unit |
| `/flow` endpoint | nạp page_nums + gọi renderer | DB + filesystem | integration nhẹ |

## Kiểm thử & kiểm chứng

- **Unit (`tests/test_faithful_flow.py`):**
  - emit đúng 1 `<img>` mỗi trang, đúng `src` `…/page-{n}.png`, đúng thứ tự, có `id="pg-{n}"`.
  - list rỗng → vẫn ra HTML hợp lệ (khung rỗng), không lỗi.
  - có script zoom (`btb-zoom`).
- **Integration:** endpoint trả HTML chứa `page-1.png … page-44.png` cho doc mẫu (TestClient + DBPage seed, hoặc kiểm trực tiếp số `<img>`).
- **Kiểm chứng thủ công:** mở `http://localhost:8000/api/docs/2024-wttc-introduction-to-ai/flow` → cuộn 44 trang, đối chiếu từng ảnh trong 17 ảnh lỗi cũ: TOC, QUIZ, bảng Data, ANNEX, eFootball/Serial/ANI/hallucination, TSMC, ACK, banner → **tất cả trung thực** (vì là raster gốc).

## Rủi ro & giảm thiểu

- **44 ảnh nặng** → `loading="lazy"` + nén PNG sẵn có; chấp nhận với ưu tiên faithfulness.
- **View "Dịch" tạm mất overlay dịch** → có chủ đích, B2 khôi phục; ghi chú rõ trong code/endpoint.
- **Trang thiếu raster** (doc lỗi extract) → endpoint lọc theo file tồn tại; trang thiếu đơn giản bị bỏ qua (không vỡ).
- **Raster 144 DPI hơi mềm khi zoom lớn** → B-sau có thể tăng `images_scale`; không chặn B1.
