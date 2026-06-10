# Faithful SVG Reader — Thiết kế (PDF → HTML giữ nguyên bản)

> **Ngày:** 2026-06-10
> **Trạng thái:** Spec để review
> **Phạm vi đợt này:** Backend (pipeline trích xuất + endpoint phục vụ + tests). Frontend toggle để đợt sau.

## 1. Bối cảnh & Vấn đề

App `break_the_barriers` chuyển PDF → HTML rồi dịch (Gemini). Pipeline hiện tại đã đi qua nhiều thế hệ
(`pdftohtml`, Docling reflow, PageModel raster+overlay, flow renderer) với ~30 service chồng nhau và **không
giữ được nguyên bản tài liệu gốc**. Các vấn đề gốc rễ đã xác minh bằng thực nghiệm:

- `pdftohtml` ở máy là bản cổ **v0.40 (2003), encoding ISO-8859-1** → hỏng Unicode, không dùng được cho tiếng Việt.
- Cơ chế raster + overlay text dịch lên đúng vị trí gây bug overlap (L3), text-fitting phức tạp, dễ sai.
- Reflow của Docling mất layout/bảng/đồ hoạ khi dùng làm bản "gốc".

## 2. Mục tiêu

Người đọc **toggle toàn trang giữa Gốc ↔ Dịch**:

- **Gốc**: hiển thị **pixel y hệt PDF** (trung thực tuyệt đối), có thể bôi đen/copy chữ.
- **Dịch**: reflow sạch, dễ đọc, đúng cấu trúc (heading, list, bảng), toàn trang.

Hai view **độc lập hoàn toàn** — bản Gốc không bao giờ phải đè text dịch lên. Đây là quyết định kiến trúc
then chốt giúp loại bỏ toàn bộ lớp lỗi overlay.

## 3. Quyết định kỹ thuật (đã chốt với chủ dự án)

| Hạng mục | Lựa chọn | Lý do |
|---|---|---|
| Render Gốc | **PyMuPDF `get_svg_image()` + lớp text vô hình** | Vector pixel y hệt (thực nghiệm 5/5), zoom nét, 0 dependency mới; lớp text bbox phủ khớp để copy |
| Trích cấu trúc Dịch | **Docling (ép CPU, `do_ocr=False`)** | Nhận diện heading/list/**bảng thật** tốt; đã cài sẵn |
| Hiển thị | Toggle toàn trang Gốc ↔ Dịch | Không overlay, không chia cột → đơn giản tối đa |
| Phạm vi đợt này | Backend-first | Verify bằng tests + curl trước khi đụng frontend |

**Cơ sở thực nghiệm** (agent đã render & so pixel trên `2024-wttc-introduction-to-ai.pdf`, 3 trang khó):
SVG của PyMuPDF cùng hệ toạ độ điểm với text bbox của `get_text("dict")` → lớp text vô hình phủ khớp 100%.
Đây chính là mô hình pdf.js nhưng **render sẵn ở server**, không phải ship cả PDF cho client.

## 4. Kiến trúc

```
                 ┌─ page.get_svg_image()  → {doc}-{n}.svg            ┐
PDF ─ fitz ──────┤  page.get_text("dict") → {doc}-{n}.textlayer.json ├─→ DBPage
                 └─ Docling (CPU)         → {doc}-{n}.html (reflow,   ┘
                                              span id) ─→ DBTranslation ─→ translator_v2

GET /api/docs/{id}/pages/{n}?view=goc  → render_faithful_page()  → SVG + lớp span trong suốt
GET /api/docs/{id}/pages/{n}?view=dich → reflow HTML + inject_translation()
```

### 4.1 Các đơn vị code (mỗi file một trách nhiệm)

| File | Trách nhiệm | Phụ thuộc |
|---|---|---|
| `app/services/faithful_extractor.py` (mới) | `FaithfulExtractor.extract_pdf()`: mỗi trang sinh SVG + text_layer JSON + reflow HTML. Trả về list per-page artifact paths. | `fitz`, `docling`, `bs4` |
| `app/services/faithful_renderer.py` (mới) | `render_faithful_page(visual, text_layer, page_w, page_h)`: ráp HTML Gốc = lớp ảnh nền (SVG inline hoặc `<img>` JPG) + các `<span>` trong suốt định vị bbox. | thuần Python (string) |
| `app/services/text_layer.py` (mới) | `build_text_layer(page)`: từ `get_text("dict")` → list `{bbox:[x,y,w,h], text}`. `reflow_blocks(page)`: fallback PyMuPDF blocks → tagged blocks khi Docling lỗi. | `fitz` |
| `app/routers/extraction.py` (sửa) | Dùng `FaithfulExtractor` thay `DoclingExtractor` ở nhánh PDF; đọc 3 sidecar vào `DBPage`. | — |
| `app/routers/documents.py` (sửa) | Thêm `view=goc|dich` vào `get_page_content`; `goc` → `render_faithful_page`, `dich` → reflow + inject. | — |
| `app/models_db.py` (sửa) | Thêm 2 cột `DBPage`: `svg_path`, `text_layer_json`. | — |

**Tái sử dụng nguyên trạng:** `translator_v2.py` (dịch per-span), `Compiler.inject_translation()` (chèn bản dịch
vào reflow HTML), `Extractor.extract_spans()` (rút span → DBTranslation), `semantic_tagger.tag_blocks()`
(role cho fallback reflow), `_items_to_page_html` pattern (reflow HTML có span id).

## 5. Hợp đồng dữ liệu

### 5.1 Sidecar mỗi trang (ghi cạnh HTML trong `data/extracted_html/{doc_id}/`)

- `{doc}-{n}.svg` — nội dung từ `page.get_svg_image()` (hoặc `{doc}-{n}.jpg` khi fallback raster).
- `{doc}-{n}.textlayer.json` — `{"page_w": float, "page_h": float, "spans": [{"bbox":[x,y,w,h], "text": str}, ...]}` (toạ độ PDF points, gốc top-left).
- `{doc}-{n}.html` — reflow HTML ngữ nghĩa, mỗi đoạn dịch được bọc `<span id="sN">text gốc</span>`.

### 5.2 DB

`DBPage` thêm:
```python
svg_path        = Column(Text, nullable=True)   # tên file visual nền: "{doc}-{n}.svg" hoặc "...jpg"
text_layer_json = Column(Text, nullable=True)   # JSON lớp text vô hình của view Gốc
```
- `original_html` (đã có) ← chứa **reflow HTML** (ngôn ngữ gốc, span id) = nguồn dịch + nền view Dịch.
- `DBTranslation` (đã có) ← `span_id → original_text/translated_text` (translator_v2 không đổi).
- `model_json`, `layout_json` ← ngừng dùng ở path mới (giữ cột, để rollback).

**Migration Postgres** (SQLite test tự tạo từ model):
```sql
ALTER TABLE pages ADD COLUMN svg_path TEXT;
ALTER TABLE pages ADD COLUMN text_layer_json TEXT;
```

### 5.3 Endpoint `GET /api/docs/{id}/pages/{n}`

Thêm tham số `view: Optional[str] = Query(None, pattern="^(goc|dich)$")`.

- `view=goc`: dựng HTML = visual nền + lớp span trong suốt. `raw=true` → `HTMLResponse` (iframe). Script postMessage `page_size` đọc kích thước từ container width/height (giữ hợp đồng cũ).
- `view=dich`: `Compiler.inject_translation(page.original_html, trans_dict)` với `trans_dict` từ `DBTranslation.translated_text` (như nhánh hiện tại). `lang` chọn ngôn ngữ đích.
- `view=None` (mặc định, không truyền): rơi xuống **nguyên hành vi cũ** theo `lang=en|vi` (model_json/layout_json/original_html) → tương thích ngược 100% cho tới khi frontend chuyển sang `view`.

### 5.4 Render Gốc — cấu trúc HTML

```html
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  .ff-page{position:relative;width:{W}px;height:{H}px;margin:0 auto}
  .ff-page svg{position:absolute;inset:0;width:100%;height:100%}
  .ff-tl{position:absolute;color:transparent;white-space:pre;
         transform-origin:0 0;pointer-events:auto;user-select:text}
</style></head><body>
  <div class="ff-page">
    {svg_inline}                          <!-- hoặc <img src=".../assets/{doc}-{n}.jpg"> -->
    <span class="ff-tl" style="left:{x}px;top:{y}px">…text…</span>  <!-- mỗi span text_layer -->
  </div>
</body></html>
```
`W/H` = page_w/page_h (PDF points). SVG nội tại đã ở cùng toạ độ → span định vị trực tiếp bằng bbox.

## 6. Xử lý lỗi (per-page guard — 1 trang lỗi không làm hỏng cả doc)

- `get_svg_image()` lỗi 1 trang → render raster `page.get_pixmap(matrix=2x)` lưu `.jpg`; `svg_path` giữ tên `.jpg`; renderer phát hiện đuôi `.jpg` → dùng `<img>` thay vì inline SVG. Vẫn pixel y hệt.
- Docling lỗi (cả doc hoặc 1 trang) → reflow fallback bằng `text_layer.reflow_blocks()` (PyMuPDF blocks + `semantic_tagger`).
- Toàn bộ extraction giữ structure cũ: per-page trong try/except, log warning, tiếp tục.

## 7. Kế hoạch test (TDD)

Fixture: tạo PDF 1–2 trang xác định bằng `fitz` trong `conftest` (text + 1 heading + 1 bảng đơn giản) — không phụ thuộc PDF lớn.

- `test_faithful_extractor.py`: extract → tồn tại `.svg`, `.textlayer.json` (spans có bbox 4 số + text), `.html` (có `<span id=...>`).
- `test_text_layer.py`: `build_text_layer` trả spans bbox dương; `reflow_blocks` fallback trả blocks có role.
- `test_faithful_renderer.py`: `render_faithful_page` chứa chuỗi SVG + có `class="ff-tl"` định vị; nhánh `.jpg` dùng `<img>`.
- `test_api.py` (bổ sung): `view=goc` trả HTML chứa SVG/`ff-tl`; `view=dich` trả reflow có `translated_text` đã chèn; `raw=true` trả `HTMLResponse` có script `page_size`.
- Fallback: ép `get_svg_image` raise → artifact `.jpg` được tạo, renderer xử lý đúng.

Chạy: `cd apps/break_the_barriers/backend && .venv/bin/pytest tests/ -v` (SQLite in-memory).

## 8. Dọn dẹp (task riêng, SAU khi path mới verify)

Các service của cơ chế overlay/flow cũ thành thừa khi frontend chuyển hẳn sang `view`:
`overlay_renderer`, `text_layer_renderer`, `page_renderer`, `page_model`, `text_fitter`, `design_region`,
`figure_extractor`, `figure_grouper`, `figure_text_detector`, `image_cleaner`, `picture_classifier`,
`page_eligibility`, `page_classifier`, `typography_extractor`, `page_image`, `faithful_flow_renderer`,
`flow_model`, `flow_renderer`. **Không xoá trong đợt này** — xoá ở task cleanup riêng sau khi verify + frontend chuyển đổi.

## 9. Ngoài phạm vi đợt này (YAGNI)

- Frontend toggle (Next.js / static reader) — đợt sau.
- Export PDF/EPUB.
- Xoá service cũ.
- Bilingual hover overlay (đã bỏ theo lựa chọn toggle toàn trang).
