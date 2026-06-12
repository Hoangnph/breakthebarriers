# F1 — Document Flow Model + Renderer cơ bản — Thiết kế

Ngày: 2026-06-06
Nhánh dự kiến: nhánh mới từ `main` (vd `feat/document-flow`)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

Sub-project **F1/4** của hướng "Flow là chính (hybrid)" (F2 section+nav · F3 frontend · F4 per-section translate).

## Bối cảnh

Layout-trung-thành-trang ép chữ dịch (dài hơn) vào hình học cố định → clip/đè/co-li-ti/mất-chữ; trình bày khó đẹp. Chuyển sang **tài liệu HTML flow (cuộn dọc)**: chữ dài chỉ chiếm thêm chiều cao. F1 dựng nền móng: gộp các PageModel → một danh sách flow elements → render HTML semantic. Dựng **từ PageModel hiện có** (blocks+role+font+thứ tự), KHÔNG đụng extraction.

## Định tuyến trang (kế thừa `effective_policy`)

Mỗi trang định tuyến bằng `effective_policy(page_class, cover, background.policy_override)`:
- `base-color` (text/nội dung) → **flow** các block thành text element + figures inline.
- `clean-photo` / `keep-raster` (bìa/sơ đồ thiết kế) → thêm một **`image_block`** (ảnh trang full-width: `clean_image` nếu clean-photo, else `image`) RỒI vẫn flow text block của trang (vd tiêu đề bìa thành heading sau ảnh).

## Thành phần

### A. `flow_model.py` (mới)
```python
@dataclass
class FlowElement:
    kind: str               # heading | paragraph | caption | list | figure | image_block
    span_id: str | None = None   # text element → tra translations
    level: int = 0          # heading: 1..3
    src: str | None = None  # figure/image_block: filename

def build_document_flow(pages: list[PageModel]) -> list[FlowElement]
```
Logic:
1. **Body font size** = mode của `font.size` các block `role=="body"` (mặc định 11.0 nếu trống).
2. **Heading**: block là heading nếu `role=="heading"` HOẶC `font.size >= body_size * 1.3`.
3. **Cấp heading**: tập font-size các heading, sort giảm dần; size lớn nhất→level 1, kế→2, còn lại→3 (cap 3).
4. Duyệt từng trang theo thứ tự:
   - Nếu policy ∈ {clean-photo, keep-raster} và có ảnh → `FlowElement(kind="image_block", src=<clean_image|image>)`.
   - Gộp blocks + figures của trang, **sort theo `bbox` top** (thứ tự đọc top-to-bottom, đan xen figure):
     - block heading → `heading` (level), `role=="caption"` → `caption`, `role=="list"` → `list`, còn lại → `paragraph`; mỗi cái giữ `span_id`.
     - figure → `figure` với `src = clean_img or img`.

### B. `flow_renderer.py` (mới)
```python
def render_flow_html(flow: list[FlowElement], translations: dict, image_url_base: str) -> str
```
- HTML cuộn dọc, một cột đọc căn giữa (`max-width: 720px`), typography dễ đọc.
- text element: tra `translations[span_id]`; bỏ qua nếu rỗng. Map kind→thẻ:
  `heading`→`<h{level}>`, `paragraph`→`<p>`, `caption`→`<figcaption>`/`<p class=cap>`, `list`→`<li>` (bọc trong `<ul>` khi liên tiếp — v1 có thể để `<p class=li>` cho gọn). Mỗi text element có `data-span="{span_id}"` (cho dịch/sửa sau, click-to-edit F4).
- `figure` → `<figure><img class="fl-fig" src="{base}/{src}"></figure>`.
- `image_block` → `<img class="fl-page" src="{base}/{src}">` (full-width).
- escape mọi text/attr.

### C. Endpoint `GET /api/docs/{id}/flow?lang=en|vi`
- Nạp mọi `DBPage` của doc (order `page_num`) → `PageModel.from_json`.
- Gom `DBTranslation` (theo lang: en→original_text, vi→translated_text) → dict `span_id→text`.
- `flow = build_document_flow(pages)`; `html = render_flow_html(flow, trans, image_base)`.
- `image_base = .../api/docs/{id}/assets`. Trả `HTMLResponse`.

## Kiểm thử (TDD)

- `build_document_flow`:
  - 2 trang tổng hợp: trang 1 `clean-photo` (cover) có 1 heading block; trang 2 `text` có body + caption + 1 figure. Kết quả: `[image_block, heading(level1), …, paragraph, caption, figure]` đúng thứ tự (figure đan theo top).
  - heading level: 2 cỡ font heading khác nhau → level 1 và 2.
  - trang `base-color` không sinh `image_block`.
- `render_flow_html`: heading→`<h1>`, paragraph→`<p>` có `data-span`, chữ dịch đúng; span không có dịch → bỏ; `image_block`→`<img class="fl-page">`; figure→`<figure>`. Escape.
- Endpoint (`TestClient`): seed 2 page model_json + translations → `GET /flow?lang=vi` → 200, HTML chứa chữ dịch trong thẻ flow + ảnh trang.

## Ngoài phạm vi F1

- Section/heading-hierarchy lồng nhau + nav TOC (F2).
- Frontend Flow view (F3).
- Per-section AI translate / manual edit (F4).
- Đa cột, nối đoạn qua trang, bảng phức tạp.

## Các file đụng tới

- Tạo: `app/services/flow_model.py`, `app/services/flow_renderer.py`.
- Sửa: `app/routers/documents.py` (endpoint `/flow`) — dùng `effective_policy` từ `background_policy`.
- Test: `tests/test_flow_model.py`, `tests/test_flow_renderer.py` (mới), bổ sung test endpoint trong `tests/test_preview_pagemodel.py`.
