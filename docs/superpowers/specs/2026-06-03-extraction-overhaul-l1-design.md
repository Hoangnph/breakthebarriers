# Extraction Overhaul (L1) — PyMuPDF text source + LLM noise filter

**Ngày:** 2026-06-03
**App:** `apps/break_the_barriers`
**Tiền đề:** Tiếp nối SP-A (faithful text-layer). Đây là SP-A.1.
**Trạng thái:** Design — chờ duyệt trước khi lập plan.

---

## 1. Bối cảnh & bằng chứng

Trên trang 2 (CONTENTS) của `2024-wttc-introduction-to-ai`, chất lượng bản dịch kém. Điều tra dữ liệu thật:

- Page 2 chỉ có **12 span**; **không span nào** là nội dung mục lục. `original_html` không chứa "FOREWORD"/"Algorithms"/`<table>`. → **docling bỏ sót toàn bộ bảng mục lục** (chữ nằm trên nền ảnh / layout phức tạp). Không có span → không dịch được → tiếng Anh lộ ra từ ảnh raster.
- 6/12 span lại là **nhiễu trang trí** từ ảnh thiết kế: `s1=/0/0/`, `s4=LC88.01`, `s6=85:1254:20`, `s7=PO52.06`, `s11=206.`, `s12=14.687.` → bị overlay thành "ký tự lạ".

Tức **docling bắt rác nhưng bỏ nội dung thật**. Đây là gốc của 2/3 lỗi người dùng nêu ("không dịch hết" + "ký tự lạ"). PyMuPDF (`fitz`, đã cài ở SP-A) trích được *toàn bộ* glyph kèm bbox/font — công cụ vá đã có sẵn, chỉ chưa dùng làm nguồn text.

## 2. Mục tiêu & phi-mục tiêu

**Mục tiêu (L1):**
- Trích **đầy đủ** text mỗi trang (gồm mục lục, chữ trên ảnh) bằng PyMuPDF làm nguồn chính.
- **Loại nhiễu trang trí** (số/mã trang trí trong ảnh) khỏi span/translation/overlay.
- Giữ vai trò ngữ nghĩa (heading/list/table/caption) và figure bằng docling (đối chiếu bbox).
- Block dịch là đơn vị mạch lạc (không vỡ vụn kiểu `14.687.`).

**Phi-mục tiêu (tách spec sau — L2):**
- Sửa render trang ảnh/mixed (inpaint chữ gốc + fit chuẩn, bỏ hộp đặc). Trang image/mixed **vẫn** overlay trên raster cho tới khi làm L2.

**Tiêu chí thành công:**
- Re-extract WTTC trang 2: các mục lục (FOREWORD, Algorithms…) **có** trong content block; rác (`206.`, `LC88.01`, `/0/0/`, `85:1254:20`, `PO52.06`, `14.687.`) **bị loại**.
- Không hồi quy: các trang chữ thường vẫn ra block/role hợp lý; test suite hiện có vẫn xanh.

## 3. Kiến trúc

```
PDF
 ├─ PyMuPDF  → TOÀN BỘ text block (bbox + font + text)        ← nguồn text chính
 └─ docling  → nhãn semantic (heading/list/table/caption) + figure regions
        │  merge theo overlap bbox → gán role cho từng block
        ▼
   ContentClassifier (gộp vào call batch-translate) → loại block 'decoration'
        │   fallback luật khi pytest / không API key
        ▼
   Clean content blocks → spans/HTML + layout.json + model.json → translate → render
```

**Đảo nguồn text:** trước đây docling là nguồn text (sót). Giờ PyMuPDF là nguồn text (đủ); docling chỉ gán nhãn + figure.

## 4. Thành phần

### 4.1 PdfTextExtractor (PyMuPDF) — `app/services/pdf_text_extractor.py`
- Input: `pdf_path`, `page_no`, `page_size`.
- Dùng `page.get_text("dict")` lấy mọi line/span; **gom span → block logic**: cụm theo toạ độ y (cùng dòng), nối dòng liền kề thành đoạn/dòng-mục-lục theo khoảng cách dọc & lề trái; mỗi block giữ `{text, bbox:[l,t,w,h] top-left, font:{size,weight,italic,color,align,family_class}}`.
- Trả danh sách block theo thứ tự đọc (trên→dưới, trái→phải).
- Tái dùng helper sẵn có ở `typography_extractor.py` (aggregate_font, classify_font_family, color, bold/italic).
- **Degrade:** lỗi/không có text → trả `[]`.

### 4.2 SemanticTagger — `app/services/semantic_tagger.py`
- Input: block của PdfTextExtractor + danh sách item docling (label + bbox) + figure regions.
- Với mỗi block, tìm item docling overlap (IoU cao nhất) → gán `role` (heading/list/table/caption/body); không match → `body`.
- Trả block kèm `role`, và danh sách `figures` (từ docling picture regions, đã có ở extractor).
- **Degrade:** docling lỗi → mọi block `role=body`, figures rỗng.

### 4.3 ContentClassifier (gộp vào batch-translate) — sửa `translator_v2.py`
- Mở rộng `_gemini_batch_translate`: schema input mỗi block `{id, text}`; **schema output** `{id, text (đã dịch), is_content (bool)}`. Prompt thêm chỉ dẫn: "đánh dấu `is_content=false` cho mảnh trang trí (số/mã/nhiễu không phải nội dung)".
- Block `is_content=false` → **loại** khỏi kết quả (không ghi DBTranslation, không vào overlay).
- **Không thêm call** — phân loại đi cùng dịch.
- **Fallback (pytest/không API key):** dùng luật `is_decoration(text)` — token ngắn (≤ ~6 ký tự thực), tỉ lệ chữ-số/dấu cao, không có khoảng trắng từ-ngữ → decoration. Deterministic, test được.
- TM (translation memory) chỉ lưu/đọc cho block `is_content=true`.

### 4.4 Pipeline rewire — sửa `extractor.py`
- `DoclingExtractor.extract_pdf_to_html`: thay nguồn block. Thứ tự:
  1. Chạy docling (như cũ) để có item labels + figure regions + raster + page_size.
  2. Chạy PdfTextExtractor (PyMuPDF) lấy text block đầy đủ.
  3. SemanticTagger gán role + figures.
  4. Dựng `original_html` (semantic theo role), spans (`s1..`), `.layout.json`, `.model.json` từ block đã tag.
- DBTranslation rows tạo từ content block; ContentClassifier (ở bước dịch) loại decoration trước khi ghi/overlay.
- **Degrade:** PyMuPDF lỗi cả trang → fallback luồng docling-only hiện tại.

## 5. Luồng dữ liệu

PDF → docling(labels+figures+raster) + PyMuPDF(text blocks) → SemanticTagger(merge→role) → extractor dựng spans/HTML/layout/model → translate-batch (dịch + phân loại content/decoration, loại decoration) → ghi DBTranslation/model → render (image/mixed: overlay raster — như cũ; text: text-layer SP-A).

## 6. Xử lý lỗi / degrade

| Tình huống | Hành vi |
|---|---|
| PyMuPDF lỗi 1 trang | fallback docling-only (hành vi hiện tại) |
| docling lỗi | block PyMuPDF vẫn dùng, role=body, figures rỗng |
| LLM classify lỗi / pytest / không key | fallback luật `is_decoration`; nếu cả luật không chắc → giữ block (an toàn: thà thừa còn hơn mất nội dung) |
| Trang thuần ảnh, không text | 0 block |

## 7. Testing

- **Unit:**
  - PdfTextExtractor: dict PyMuPDF giả lập → gom block đúng (cùng dòng gộp, đoạn tách đúng), bbox/font đúng.
  - SemanticTagger: gán role theo overlap bbox (heading/list/table/body) với item giả lập.
  - ContentClassifier fallback: `is_decoration` đúng cho `206.`,`LC88.01`,`/0/0/`,`85:1254:20`; `False` cho "Brief history of Artificial Intelligence".
  - `_gemini_batch_translate` (mock): output có `is_content`; block false bị loại.
- **Integration (PDF thật WTTC):** re-extract → trang 2 content block chứa mục lục; rác bị loại; trang chữ thường không hồi quy.
- Test dùng SQLite in-memory + mock Gemini (pattern `is_pytest` sẵn có).

## 8. Phạm vi & phân rã
- **L1 (spec này):** components 4.1–4.4. Sửa "không dịch hết" + "ký tự lạ".
- **L2 (spec riêng sau):** render trang image/mixed (inpaint chữ gốc + fit chuẩn, bỏ hộp đặc) để sửa "che nội dung".
- **Vận hành:** tài liệu cũ phải **extract lại** mới hưởng lợi (giống SP-A). Không có migration dữ liệu cũ.

## 9. Câu hỏi mở (chốt ở plan, không chặn duyệt)
- Ngưỡng gom block của PdfTextExtractor (khoảng cách dọc/ngang để tách dòng↔đoạn↔mục-lục-entry).
- Ngưỡng IoU SemanticTagger gán role.
- Bộ luật cụ thể của `is_decoration` (độ dài, tỉ lệ ký tự số/mã).
- Thứ tự đọc cho layout nhiều cột (nếu có) — tạm theo y rồi x.
