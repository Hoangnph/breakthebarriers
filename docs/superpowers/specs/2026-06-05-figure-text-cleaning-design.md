# Figure Text Cleaning — Thiết kế (#2)

Ngày: 2026-06-05
Nhánh dự kiến: tiếp tục `feat/manual-per-page`
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

Việc **#2/3** hậu-verify (1. classifier ✓ · 2. figure-có-chữ ← đây · 3. cấu trúc TOC).

## Bối cảnh & vấn đề

Một số figure là **banner/hình có chữ nung sẵn** (vd banner "FOREWORD" trang 3).
Khi render, figure crop hiển thị nguyên chữ Anh; overlay tiêu đề dịch ("LỜI NÓI
ĐẦU") của ta nằm cạnh/đè → **ghost**. Ta đã làm sạch raster nền (CleanPage) nhưng
**chưa làm sạch chữ trong figure**.

## Quyết định đã chốt

- Chỉ **XÓA** chữ trong figure (không vẽ lại chữ Việt vào figure) — để overlay
  bản dịch của ta hiển thị sạch.
- **Auto-detect (offline, lúc extract) + auto-clean (AI, lúc extract).**
- Ảnh figure đã sạch là **asset trung tính ngôn ngữ**, dùng lại cho HTML + mọi
  ngôn ngữ dịch → chi phí AI một-lần là đáng.

Công cụ sẵn có: **tesseract binary** `/opt/homebrew/bin/tesseract`; đã có
`composite_inpaint` + `_gemini_clean_bytes` + `clean_page_background_inpaint`
(từ inpaint) để tái dùng.

## Thành phần

### A. `figure_text_detector.py` (mới)
`detect_text_boxes(crop_path: str, *, min_conf: int = 40, min_h_frac: float = 0.04)
-> list[tuple[int,int,int,int]]`:
- Gọi tesseract binary qua subprocess với output TSV
  (`tesseract <crop> stdout --psm 11 tsv`).
- Parse các dòng có `conf >= min_conf` và `text` không rỗng; lấy `(left, top,
  width, height)` (pixel trong figure).
- Lọc box quá nhỏ (`height < min_h_frac * img_height`) để bỏ nhiễu.
- Trả list box; **rỗng = figure không có chữ** (không cần làm sạch).
- Lỗi/không có tesseract → trả `[]` (an toàn: coi như không có chữ).

### B. `Figure.clean_img: Optional[str] = None` (page_model.py)
Tên file figure đã sạch. `to_dict` (asdict) tự kèm; `from_dict` đọc
`clean_img=f.get("clean_img")`. Default None → model.json cũ vẫn nạp.

### C. Làm sạch — `clean_page_background` (whole-clean)
**[Cập nhật sau verify]** Masked-inpaint KHÔNG hợp cho figure: tesseract đọc chữ
banner stylized (trắng-trên-nền-tối) không chuẩn → mask trật → composite giữ chữ
gốc (đã kiểm thật trên banner FOREWORD). Vì vậy:
- `detect_text_boxes` (A) chỉ dùng để **gate "figure có chữ"** (bỏ qua figure
  không chữ, khỏi tốn AI).
- Figure có chữ → **whole-clean** `clean_page_background(crop, clean)` (AI xóa
  chữ toàn ảnh, tin cậy). Figure trang trí chịu được việc vẽ lại. Người dùng đã
  chọn whole-clean cho MỌI figure có chữ (không gate theo photo).
- Cover vẫn dùng masked-inpaint (bbox block tin cậy) — không đổi.

### D. Extractor wiring
Sau khi crop mỗi figure (đã có `crop_figure` → filename), nếu được phép gọi AI:
- `boxes = detect_text_boxes(crop_path)`; nếu rỗng → bỏ qua (figure không chữ).
- `clean_name = "<fig>.clean.png"`; nếu chưa tồn tại →
  `clean_page_background_inpaint(crop_path, clean_path, boxes)`.
- Thành công → `figure.clean_img = clean_name`. Lỗi/không key → giữ figure gốc
  (fail-safe, không vỡ extraction).
- **Guard không gọi mạng khi test**: bỏ qua bước AI khi
  `os.getenv("PYTEST_CURRENT_TEST")` được set HOẶC không có `GEMINI_API_KEY`.
  (`detect_text_boxes` offline vẫn có thể chạy, nhưng nếu không clean thì không
  set clean_img — an toàn.)

### E. Renderer
Trong vòng vẽ figure của `render_text_layer`: dùng `fig.clean_img` nếu có, else
`fig.img`:
```python
fig_src = fig.clean_img or fig.img
```

## Luồng & tái sử dụng asset

Extract → figure có chữ → `<fig>.clean.png` (1 lần, AI) → lưu `figure.clean_img`
trong model_json. Mọi lần render (HTML/EN/VI/ngôn ngữ khác) dùng chung ảnh sạch
đó + overlay chữ dịch tương ứng. Chi phí AI một-lần, dùng vô hạn.

## Kiểm thử (TDD)

- `detect_text_boxes`: tạo ảnh có chữ rõ (PIL/cv2 `putText` "FOREWORD") → trả ≥1
  box; ảnh trơn một màu → `[]`; đường dẫn không đọc được → `[]`.
- `render_text_layer`: figure có `clean_img="f.clean.png"` → HTML chứa
  `f.clean.png`, KHÔNG chứa `f.png` gốc; figure không clean_img → dùng `f.img`.
- `Figure`/`PageModel` round-trip giữ `clean_img`; model.json cũ (thiếu) → None.
- Wiring extractor: verify qua **backfill** trên doc thật (banner trang 3 hết chữ).

## Ngoài phạm vi

- Dịch chữ trong figure sang tiếng Việt (chỉ xóa).
- Manual per-figure trigger (đã chọn auto lúc extract).
- Cấu trúc TOC (#3).

## Các file đụng tới

- Tạo: `app/services/figure_text_detector.py`.
- Sửa: `app/services/page_model.py` (Figure.clean_img),
  `app/services/text_layer_renderer.py` (figure src ưu tiên clean_img),
  `app/services/extractor.py` (detect + clean figure khi extract).
- Test: `tests/test_figure_text_detector.py` (mới), bổ sung
  `tests/test_text_layer_renderer.py`, `tests/test_page_model.py`.
- (Verify) cập nhật `scripts/relabel_document.py` hoặc script one-off để
  detect+clean figure cho doc đã extract.
