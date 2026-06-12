# Faithful Overlay Translation — Design Spec

**Goal:** Hiển thị bản dịch giữ trung thực nền/ảnh/hoạ tiết của trang PDF gốc, đồng thời giữ nguyên chất lượng dịch của engine V2 (glossary/TM/context). Đạt được bằng cách dùng **ảnh raster trang gốc làm nền** + **lớp text dịch định vị tuyệt đối** đè lên đúng vị trí khối chữ gốc.

**Bối cảnh:** Pipeline hiện tại dùng DoclingExtractor sinh HTML ngữ nghĩa (reflow) → mất toàn bộ ảnh (`<img src="">` rỗng cứng tại `extractor.py:361`) và nền/layout gốc. Đây là đánh đổi cố hữu của trích xuất ngữ nghĩa. Phương án này bổ sung một lớp hiển thị trung thực mà **không** thay engine dịch và **không** đổi mô hình phục vụ HTML/web-reader.

**Tham chiếu thế giới:** SOTA hiện tại là BabelDOC / PDFMathTranslate (EMNLP 2025) — dùng DocLayout-YOLO + reposition để tái dựng PDF song ngữ. Spec này chọn biến thể "raster nền + overlay text" vì giữ được engine V2 và output HTML khớp hệ thống hiện có (xem mục Alternatives).

---

## Non-Goals (Out of Scope)

- OCR cho PDF scan (PDF ảnh thuần không có text layer) — phase sau.
- Xuất PDF song ngữ để tải về (hướng BabelDOC) — phase sau nếu cần.
- Inpaint/xoá chữ gốc khỏi ảnh raster — v1 dùng hộp màu sampling để che.
- Đo font bằng JS runtime — v1 dùng công thức + wrap.
- Đụng tới engine dịch `translator_v2.py` hay bảng `translations`.

---

## Architecture

```
PDF
 ├─(1) pdftoppm (poppler /opt/homebrew/bin) → page-{n}.png        [nền trung thực]
 └─(2) Docling (giữ nguyên)                 → khối text + bbox + page_size
                                                   │
                (3) V2 engine dịch khối (GIỮ NGUYÊN) → translated_text per span
                                                   │
                (4) overlay_renderer (mới): layout_json + translated_text
                                            → HTML positioned (nền <img> + <div> text)
                                                   │
                (5) lưu vào DBPage.translated_html → phục vụ qua /pages/{n}?lang=vi
```

**Bất biến giữ được "cả hai":**
- Chất lượng dịch: bước (3) không đổi.
- Trung thực nền/ảnh: nền là ảnh raster trang gốc ở bước (1).
- Tương thích: output là HTML trong `translated_html`; reader hiện tại render thẳng (`dangerouslySetInnerHTML`/`iframe`). `lang=en` trả raster gốc (trung thực tuyệt đối); `lang=vi` trả overlay.

---

## Data Model Changes

Thêm **một** cột nullable, không phá đường cũ:

```sql
ALTER TABLE pages ADD COLUMN IF NOT EXISTS layout_json TEXT;
```

`DBPage.layout_json` chứa JSON:

```json
{
  "page_w": 595.0,
  "page_h": 842.0,
  "image": "page-3.png",
  "blocks": [
    {"span_id": "s1", "bbox": [72.0, 700.0, 200.0, 24.0], "font_size": 18.0, "color": "#1a1a1a"}
  ]
}
```

- `bbox` = `[x, y, w, h]` theo **điểm PDF**, đã chuẩn hoá về gốc trên-trái (xem 2.1).
- `DBTranslation` **không đổi** — overlay đọc `layout_json.blocks[].span_id` rồi tra `translated_text` từ bảng `translations`.
- `image=null` ⇒ trang không có raster (fallback flow HTML cũ).

---

## Components

### `services/page_raster.py` (mới)

```python
def render_page_images(pdf_path: str, output_dir: str, doc_id: str, dpi: int = 200) -> dict[int, str]:
    """Render mỗi trang PDF → PNG bằng pdftoppm. Trả {page_no: filename}."""

def sample_bg_color(image_path: str, bbox_px: tuple[int,int,int,int]) -> str:
    """Lấy màu nền vùng bbox (median pixel viền) bằng Pillow → '#rrggbb'.
    Lỗi/đọc không được → '#ffffff'."""
```

- `render_page_images`: gọi `pdftoppm -png -r {dpi}` (poppler đã cài). Tên file `page-{n}.png` trong `extracted_html/{doc_id}/`.
- `sample_bg_color`: mở PNG (Pillow), lấy các pixel trên viền bbox, trả median dạng hex.

### `services/extractor.py` (sửa `DoclingExtractor`)

- Thu thập per-page: `page_w, page_h` (từ `PageItem.size`), và mỗi text item: `span_id` (đồng bộ với span id đang sinh trong `_items_to_page_html`), `bbox` (từ `item.prov[0].bbox`), `font_size`/`color` nếu có (nếu không, để `null` → renderer dùng mặc định).
- Sinh `layout_json` cho mỗi trang; trả về cùng danh sách html_files như cũ (đường flow HTML giữ làm fallback).
- **Lưu ý đồng bộ span_id:** bbox phải gắn đúng `span_id` mà `_items_to_page_html` gán cho cùng text item, để overlay tra cứu khớp với bảng `translations`.

### `services/overlay_renderer.py` (mới)

```python
def render_overlay_html(layout: dict, translations: dict[str, str], image_url_base: str) -> str:
    """layout=layout_json đã parse; translations={span_id: translated_text}.
    Trả HTML: container aspect-ratio page_w/page_h, nền <img>, mỗi block là
    <div position:absolute left/top/width theo %> chứa text dịch."""
```

- Container: `position:relative; aspect-ratio: page_w/page_h;` nền `<img src="{image_url_base}/{image}">` phủ kín.
- Mỗi block: `left=x/page_w*100%`, `top=y/page_h*100%`, `width=w/page_w*100%`, `height:auto`, `font-size`, `color`, `background` (màu sampling), `overflow:hidden`, cho phép wrap.
- Escape HTML text dịch. Thiếu `translated_text` cho span → dùng nguyên text gốc (đã có trong layout? không — fallback: bỏ trống/giữ gốc nếu cần).
- `image=null` hoặc block thiếu bbox → render flow fallback (tái dùng HTML ngữ nghĩa cũ).

### `routers/extraction.py` (sửa)

- Sau khi Docling extract, gọi `render_page_images` và build `layout_json` mỗi trang, lưu vào `DBPage.layout_json`. Giữ nguyên guard concurrency và đường mock.
- pdftoppm lỗi → `layout_json.image=null` cho trang đó (fallback), không làm hỏng cả extract.

### `routers/documents.py` (sửa endpoint `/pages/{page_num}`)

- `lang=en`: nếu có raster → trả HTML chứa **ảnh raster gốc** (trung thực tuyệt đối); không có → `original_html` như cũ.
- `lang=vi` (hoặc khác en): nếu có `layout_json.image` → `overlay_renderer.render_overlay_html(...)`; không có → `translated_html`/compile flow như cũ.

### Không đổi
- `services/translator_v2.py`, bảng `translations`, glossary, TM, tier-routing.
- Endpoint `/assets/{filename}` (phục vụ ảnh) — đã có sẵn.

---

## Coordinate System (chi tiết)

- Docling bbox theo điểm PDF; `coord_origin` có thể là `BOTTOMLEFT` hoặc `TOPLEFT`.
- Chuẩn hoá về **gốc trên-trái**: nếu `BOTTOMLEFT` → `top = page_h - (y + h)`.
- Lưu bbox đã chuẩn hoá (top-left) trong `layout_json`.
- Renderer đổi sang **%** theo `page_w/page_h` → khớp ảnh raster ở mọi DPI và responsive.

## Text Overflow (auto-fit)

- Cỡ chữ khởi điểm: `font_size × clamp(len_source/len_target, 0.6, 1.0)`.
- `height:auto` + wrap nhiều dòng; `overflow:hidden` lớp an toàn.
- Tràn nhiều sau auto-fit → set `needs_review=true` (cờ SP7 sẵn có) + log.

## Masking chữ gốc

- Mỗi block: `background = sample_bg_color(...)` để hộp text dịch che chữ gốc trong raster.
- Sampling lỗi → `#ffffff`.
- Limitation: chữ nằm trực tiếp trên ảnh/gradient → hộp màu phẳng thành "miếng vá" nhẹ (hiếm với body text; chấp nhận v1).

---

## Error Handling

| Tình huống | Xử lý |
|-----------|-------|
| pdftoppm lỗi 1 trang | `layout_json.image=null` → renderer fallback flow HTML cũ |
| Docling thiếu bbox 1 block | Block vào vùng flow fallback cuối trang + `needs_review=true` |
| Text dịch tràn hộp | Auto-fit + wrap; vẫn tràn → `needs_review=true` |
| Sampling màu lỗi | `background:#ffffff` |
| PDF scan (không text layer) | Trang chỉ có raster gốc, không overlay; ghi nhận cho OCR phase sau |

---

## Testing (TDD)

**Unit (mock — không gọi Gemini/poppler thật):**
- `overlay_renderer`: layout_json + translations → HTML đúng `left%/top%/width%`, escape, ghép đúng `span_id`, lật Y đúng.
- `page_raster.sample_bg_color`: ảnh PIL test (vùng màu biết trước) → đúng màu hex; lỗi → `#ffffff`.
- `extractor`: mock Docling items có bbox → `layout_json` có `page_w/h` + blocks (bbox + span_id + image).
- Edge: `image=null` → renderer ra flow fallback; thiếu bbox 1 block → block đó vào fallback.

**Integration:**
- Extract 1 PDF nhỏ thật (poppler thật) → assert `page-1.png` tồn tại + `layout_json` có blocks.
- Render overlay với translations giả → text dịch xuất hiện đúng vùng %.

**Regression:** 131 test hiện có vẫn pass (cột mới nullable, đường cũ không đổi).

---

## Migration

```sql
-- scripts/migrate_overlay.sql
ALTER TABLE pages ADD COLUMN IF NOT EXISTS layout_json TEXT;
```

`DBPage.layout_json = Column(Text, nullable=True)` trong `models_db.py`.

---

## Phasing

- **Phase 1 — Capture layout + raster:** migration `layout_json`; `page_raster.render_page_images`; sửa `extractor.py` thu bbox/page_size; lưu `layout_json`. Test: extract ra ảnh + layout_json.
- **Phase 2 — Overlay render + serving:** `overlay_renderer.render_overlay_html`; sửa `/pages/{n}` (`lang=en`→raster, `lang=vi`→overlay). Test: overlay HTML đúng vị trí.
- **Phase 3 — Polish:** `sample_bg_color` che chữ gốc; auto-fit font; `needs_review` khi tràn. Test: masking + overflow.

Mỗi phase ra sản phẩm chạy được, test xanh độc lập.

---

## Alternatives Considered

- **A. BabelDOC/PDFMathTranslate:** SOTA, tái dựng PDF song ngữ, trung thực cao nhất cho bản tải về. Loại khỏi v1 vì: thay engine dịch (mất glossary/TM/context V2), đổi output sang PDF (thay web reader bằng PDF.js), phụ thuộc nặng (DocLayout-YOLO/ONNX/fonts), Gemini cần OpenAI-compat shim. Cân nhắc cho phase sau (nút "Tải PDF song ngữ").
- **C. Vision-LLM dựng lại HTML:** Gemini vision sinh HTML/CSS giống trang. Loại: không tái tạo được ảnh raster, layout bấp bênh/hallucinate, khó ép glossary, đắt/trang.

---

## Self-Review
- ✅ Không TBD/placeholder.
- ✅ Backward compatible: cột nullable, `image=null`/thiếu bbox → fallback flow HTML cũ; engine V2 & bảng translations không đổi.
- ✅ Mỗi trang luôn có đường hiển thị (raster, overlay, hoặc flow fallback) — không trang trắng.
- ✅ span_id đồng bộ giữa extractor và translations (ràng buộc đã nêu rõ).
- ✅ Scope gọn cho 1 plan, chia 3 phase độc lập.

---

## Implementation Notes

- Page raster do Docling render (`generate_page_images=True`, `images_scale=2.0`),
  KHÔNG dùng pdftoppm (binary không có trên máy). Cùng một pass extract.
- Per-page raster được guard try/except: 1 trang lỗi raster sẽ degrade về flow
  HTML (image=null, blocks=[]) mà không abort cả lần extract.
- Overflow xử lý bằng auto-fit font + vertical growth (`overflow: visible`,
  không clip). Cờ `needs_review`-on-overflow tự động được hoãn (cần ghép độ
  dài bản dịch với hộp ở thời điểm dịch; ngoài scope GET phục vụ trang).
- Masking chữ gốc dùng màu sampling phẳng (validate hex, fallback #ffffff) —
  chữ trên ảnh/gradient có thể thành "miếng vá" nhẹ (giới hạn đã biết).
- `render_overlay_html` escape text + image src, validate bg color (defense-in-depth).
