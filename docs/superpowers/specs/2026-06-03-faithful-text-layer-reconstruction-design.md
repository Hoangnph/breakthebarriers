# Faithful Text-Layer Reconstruction — SP-A (Nền tảng + Preview)

**Ngày:** 2026-06-03
**Branch khởi điểm:** `feat/faithful-overlay-translation`
**App:** `apps/break_the_barriers`
**Trạng thái:** Design — chờ duyệt trước khi lập kế hoạch triển khai

---

## 1. Bối cảnh & vấn đề

Pipeline hiện tại dịch overlay theo cách: **render ảnh raster của trang gốc làm nền + phủ các `<div>` chữ dịch lên, mỗi div tô một ô màu nền đặc** (`bg` lấy mẫu từ ảnh). Logic nằm ở `backend/app/services/overlay_renderer.py`.

Ba điểm yếu gốc rễ khiến bản dịch chưa đạt production (quan sát trên trang bìa WTTC):

1. **Hộp màu đặc đè lên ảnh.** `bg` chỉ là *một* màu lấy mẫu (`sample_bg_color`). Trên nền ảnh/gradient nó tạo các mảng chữ nhật lệch tông → trần fidelity cứng.
2. **Fit font bằng heuristic thô.** `_fit_font_size` giả định `chars_per_line = box_w / (0.5 × fs)` (mọi ký tự rộng = nửa cỡ chữ). Sai với hầu hết font, đặc biệt tiếng Việt (dấu phụ, dài hơn ~30% so với tiếng Anh) → tràn hộp, xuống dòng xấu.
3. **Mất toàn bộ typography gốc.** Extractor chỉ lưu `bbox` + `bg` mỗi block (`extractor.py:376`). Không có font-family/size/weight/màu/căn lề. `line-height` cứng 1.15, màu chữ đoán theo luminance → chữ dịch không bao giờ khớp dáng bản gốc.

## 2. Mục tiêu & phi-mục tiêu

**Mục tiêu (SP-A):**
- Trang **chữ**: tái dựng HTML/CSS thật từ chữ dịch (KHÔNG dùng raster nền), khớp font/cỡ/đậm/màu/căn lề bản gốc.
- Trang **ảnh** (bìa, infographic): giữ nguyên ảnh gốc, overlay tối thiểu hoặc bỏ — không hộp đặc.
- Một **PageModel** giàu thông tin làm nguồn dữ liệu duy nhất, dùng được cho cả preview lẫn export về sau.
- Preview web song song (ORIGINAL | TRANSLATED) đạt chất lượng nhìn thấy ngay.

**Phi-mục tiêu (để SP-B):**
- Export PDF/EPUB faithful (print CSS, `@page`, phân trang). SP-A chỉ đảm bảo PageModel + HTML đủ giàu để SP-B dùng lại.
- Visual regression tự động (tùy chọn, không bắt buộc cho SP-A).

**Tiêu chí thành công SP-A:**
- Trang nội dung text: bản dịch render bằng chữ HTML thật, copy/search/zoom được, không còn hộp màu đặc, không tràn chữ ở cỡ mặc định.
- Trang bìa/ảnh: không xuất hiện hộp chữ nhật lệch tông; ảnh gốc giữ nguyên.
- Khi PyMuPDF/crop lỗi ở một trang, trang đó degrade an toàn (fallback) chứ không vỡ cả tài liệu.

## 3. Kiến trúc

```
PDF
 ├─(docling)──→ semantic + bbox + nhãn (heading/body/list/code/table/picture)
 └─(PyMuPDF)──→ font size / weight / italic / màu chữ / căn lề / font-name
        │  merge theo bbox (IoU)
        ▼
   PageModel (JSON sidecar, 1 file/trang)   ◄── nguồn duy nhất
        │
        ▼
   PageClassifier → kind: text | image | mixed
        │
        ├─ text  → TextLayerRenderer (HTML thật, KHÔNG raster)
        ├─ image → ImagePageHandler (giữ raster gốc, overlay tối thiểu)
        └─ mixed → giữ raster + text-layer cho vùng chữ
        │
        ▼
   Translator V2 (ĐÃ CÓ — dịch theo block, giữ span_id)
        │
        ▼
   Preview web (iframe song song)        [SP-B: Exporter → PDF/EPUB]
```

**Khác biệt cốt lõi:** trang chữ bỏ hẳn raster + hộp `bg` đặc → loại bỏ 3 điểm yếu mục 1. Trang ảnh giữ fidelity ảnh thật.

## 4. Thành phần

Mỗi thành phần một nhiệm vụ, interface rõ, test độc lập.

### 4.1 PageModel (data contract)
Schema trung gian, JSON sidecar `{doc_id}-{page_no}.model.json` (kế thừa pattern `.layout.json` hiện có):

```jsonc
{
  "page_w": 595.0, "page_h": 842.0,
  "kind": "text",                       // text | image | mixed
  "background": { "color": "#ffffff", "image": null },  // image != null khi mixed/image
  "blocks": [
    {
      "span_id": "s1",
      "role": "heading",                // heading|body|list|code|table|caption
      "bbox": [l, t, w, h],             // top-left points
      "text": "INTRODUCTION TO AI",
      "font": {
        "size": 24.0, "weight": 700, "italic": false,
        "color": "#1a1a1a", "align": "left",   // left|center|right|justify
        "family_class": "sans"          // serif|sans|mono
      }
    }
  ],
  "figures": [ { "bbox": [l,t,w,h], "img": "{doc_id}-{page_no}-fig1.png" } ]
}
```

`role` suy từ nhãn docling. `font` từ TypographyExtractor. Đây là nguồn duy nhất cho renderer (preview) và SP-B (export).

### 4.2 TypographyExtractor (PyMuPDF)
- Input: đường dẫn PDF + trang + danh sách block (span_id, bbox) từ docling.
- Với mỗi block, lấy các text-span PyMuPDF (`page.get_text("dict")`) giao với bbox (IoU ngưỡng cấu hình), tổng hợp: `size` (mode/median), `weight` (từ flag bold hoặc tên font), `italic`, `color`, `align` (suy từ vị trí dòng so với bbox), `font_name`.
- Map `font_name` → `family_class` (serif/sans/mono) qua bảng heuristic tên font; rồi mỗi class → font Việt-an-toàn ở tầng render (vd sans→"Be Vietnam Pro", serif→"Source Serif", mono→"JetBrains Mono"). Map cụ thể chốt ở plan.
- **Degrade:** lỗi/không match → trả `font` rỗng; renderer dùng fallback role-based (cỡ suy từ `bbox.height`).

### 4.3 FigureExtractor
- Cắt vùng `picture` bbox từ page raster 2x (PIL đã có ở `extractor.py:327`) → PNG `{doc_id}-{page_no}-figN.png`, ghi vào `figures[]`.
- Thay thế `<img src="">` rỗng hiện tại (`extractor.py:412`).
- **Degrade:** crop lỗi → giữ placeholder + `needs_review`.

### 4.4 PageClassifier (router)
- Tính tỉ lệ diện tích: `text_area = Σ block.bbox`, `fig_area = Σ figure.bbox`, so với diện tích trang.
- Quy tắc (ngưỡng cấu hình, chốt ở plan): full-bleed image hoặc fig_area chiếm đa số & ít chữ → `image`; chủ yếu chữ → `text`; còn lại → `mixed`.
- Không chắc → `mixed` (an toàn fidelity: giữ raster).

### 4.5 TextLayerRenderer
- Input: PageModel + dict bản dịch (span_id → text).
- Hai chế độ layout:
  - **flow**: trang body chuẩn → HTML semantic (`h1..h6/p/ul/table`) + CSS, reflow tự nhiên, chữ dịch dài tự xuống dòng. Ưu tiên cho trang nội dung.
  - **absolute**: trang layout đặc thù (bìa/cột/poster) → đặt block tuyệt đối theo bbox% + font khớp + TextFitter.
- Chọn mode theo độ phức tạp layout (heuristic: số cột, độ lệch baseline). Chốt tiêu chí ở plan.
- Mỗi class font khai báo `@font-face`/web font; áp `font.size/weight/italic/color/align`.

### 4.6 TextFitter
- Thay heuristic `0.5*fs`. Đo chữ thật (đo trên client bằng canvas `measureText`, hoặc ước lượng bằng bảng bề rộng ký tự ở server cho lần render đầu).
- Thứ tự ưu tiên khi bản dịch dài hơn box: (1) giữ cỡ, cho box cao thêm tới ngưỡng; (2) auto-shrink theo bước nhỏ; (3) chạm min size → cho phép cuộn/ellipsis.
- Chỉ áp ở chế độ **absolute**; chế độ **flow** để dòng chảy tự xử lý.

### 4.7 ImagePageHandler
- Trang `image`: giữ raster gốc (đường đi hiện tại), overlay tối thiểu (vd caption ngắn) hoặc bỏ overlay — tuyệt đối không hộp đặc lên ảnh.

## 5. Luồng dữ liệu

1. Extract: docling (semantic+bbox) chạy như hiện tại; thêm TypographyExtractor (PyMuPDF) + FigureExtractor → merge thành **PageModel** sidecar.
2. Classify: PageClassifier gắn `kind` vào PageModel.
3. Translate: Translator V2 (đã có) dịch theo block giữ `span_id`, ghi DBTranslation như hiện tại — **không đổi**.
4. Render preview: endpoint preview đọc PageModel + translations → chọn handler theo `kind` → trả HTML cho iframe TRANSLATED. Cột ORIGINAL giữ nguyên cơ chế hiện tại.

## 6. Xử lý lỗi / degrade

| Tình huống | Hành vi |
|---|---|
| PyMuPDF lỗi/không match 1 trang | `font` rỗng → renderer fallback role-based (cỡ từ bbox); trang vẫn render |
| Crop figure lỗi | giữ placeholder, set `needs_review` (cơ chế đã có) |
| Router không chắc | `kind=mixed` → giữ raster + text-layer vùng chữ |
| docling không cho bbox/page_size (đã xảy ra) | degrade về flow HTML như hiện tại |

Giữ nguyên cơ chế `needs_review`/`review_reason` đã có trong `translator_v2.py`.

## 7. Testing

- **Unit:**
  - TypographyExtractor: map font-name → family_class; tổng hợp size/weight/align từ spans giả lập.
  - TextFitter: đo + chuỗi ưu tiên giãn→shrink→min.
  - PageClassifier: ngưỡng text/image/mixed với bbox giả lập.
  - FigureExtractor: crop đúng vùng bbox (so kích thước/offset).
  - PageModel: serialize/deserialize, default khi thiếu font.
- **Integration:** 1 PDF thật có trang bìa (image) + trang nội dung (text) → snapshot PageModel → snapshot HTML render (text page không chứa `<img class="ov-bg">`; image page giữ raster).
- Tests dùng SQLite in-memory như hiện tại; phần gọi Gemini mock trong pytest (đã có pattern `is_pytest`).

## 8. Phạm vi triển khai SP-A

Thuộc SP-A: thành phần 4.1–4.7 + tích hợp endpoint preview.
Để SP-B (spec riêng): Exporter PDF/EPUB, print CSS/`@page`, phân trang — dùng lại PageModel.

## 9. Câu hỏi mở (chốt ở giai đoạn plan, không chặn duyệt design)
- Bảng map font-name → family_class và bộ font Việt-an-toàn cụ thể.
- Ngưỡng IoU merge bbox docling↔PyMuPDF.
- Ngưỡng diện tích phân loại text/image/mixed.
- Tiêu chí chọn flow vs absolute mode.
