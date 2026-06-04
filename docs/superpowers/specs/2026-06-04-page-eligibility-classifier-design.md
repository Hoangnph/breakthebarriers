# #0 — Page Eligibility Classifier — Thiết kế

Ngày: 2026-06-04
Nhánh dự kiến: `feat/page-eligibility-classifier` (tách khỏi L3)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

## Bối cảnh

Tính năng lớn "tái tạo nền trang ảnh + nút chất lượng dịch" gồm 4 phần:

| # | Hệ thống con | Vai trò |
|---|--------------|---------|
| **0** | **Page eligibility classifier** (tài liệu này) | Gắn nhãn mỗi trang: `text` / `preserve` / `regenerable` + `cover` |
| 1 | Standard tier — inpaint provider | Xoá chữ baked-in khỏi raster thật, phủ chữ dịch sạch |
| 2 | Premium tier — AI background gen | Sinh nền mới (image-to-image) + nút chất lượng + cache + quota |
| 3 | Manual per-page mode | UI + endpoint cho người dùng tự chọn cách xử lý từng trang |

#0 là nền móng: nó CHỈ gắn nhãn, không inpaint/sinh ảnh. Yêu cầu cốt lõi của
người dùng: **tự động chọn trang nhiều ảnh / ít chữ để tái tạo nền, nhưng TUYỆT
ĐỐI không đụng vào sơ đồ/biểu đồ (diagram/chart) — phải giữ nguyên độ chính xác.**

### Vấn đề & tín hiệu hiện có

- `page_classifier.classify_kind` chỉ phân `text|image|mixed` theo tỉ lệ diện
  tích; **không** phân biệt ảnh với sơ đồ.
- Docling gắn `label` cho mỗi item: `table` được nhận diện riêng (→ luôn
  preserve), nhưng **ảnh và biểu đồ đều trả về `"picture"`** — không tách được.
- Vì vậy bài toán duy nhất #0 phải giải: **phân biệt photo/minh hoạ vs
  sơ đồ/biểu đồ** trong các figure `picture`. Sai lầm thảm hoạ = gắn một biểu đồ
  thành `regenerable`.
- Thư viện sẵn có: PIL, numpy, OpenCV (`cv2`), PyMuPDF (`fitz`) — đủ để làm
  heuristic thị giác. Không cần thêm dependency.

### Khảo sát tài liệu mẫu (`2024-wttc-introduction-to-ai`, 44 trang)

20 `mixed` + 24 `text`, không có trang `image` thuần. Trang 1 = bìa trước
(text 24%, có figure), trang 44 = bìa sau (figure 80%). Phân bố này xác nhận:
cover nhận diện theo vị trí + tỉ lệ; nhãn phải thận trọng.

## Quyết định thiết kế đã chốt

- **Phương pháp phát hiện: hybrid** (heuristic + AI vision), nhưng **lúc extract
  chỉ chạy heuristic** — tất định, nhanh. Trang heuristic phân vân → `preserve`.
  AI vision (Gemini) để dành cho #2/#3, gọi theo yêu cầu + cache. #0 chỉ định
  nghĩa *interface* cho AI, không gọi khi extract.
- **Mặc định an toàn: mọi nghi ngờ → `preserve`.** Biểu đồ không bao giờ lọt vào
  `regenerable`.

## A. Nhãn trang (đầu ra)

Mỗi trang nhận 2 nhãn mới, tính lúc extract, lưu trong PageModel:

- `page_class ∈ {text, preserve, regenerable}`
  - `text` — ít figure → đi đường text-layer (L3). Không đủ điều kiện tái tạo.
  - `preserve` — có `table`, HOẶC có figure bị phân loại `diagram`, HOẶC bất kỳ
    figure nào `uncertain`. Giữ raster nguyên vẹn, **không bao giờ** tái tạo.
  - `regenerable` — image-dominant / ít chữ **VÀ** mọi figure `picture` đều là
    `photo` **VÀ** không có table. Đủ điều kiện cho #1/#2.
- `cover ∈ {front, back, none}` — nhãn trực giao với `page_class`.

## B. Bộ phát hiện photo-vs-diagram (heuristic, tất định)

`classify_picture(crop) -> (label, confidence)` với `label ∈
{photo, diagram, uncertain}`, đầu vào là ảnh crop figure (đã có sẵn trên đĩa).

Các đặc trưng tính trên crop (thu nhỏ ≤256px để nhanh, dùng cv2/numpy):
1. **unique_colors** — số màu phân biệt sau lượng tử hoá (vd 4 bit/kênh),
   chuẩn hoá theo diện tích. Photo cao, sơ đồ thấp.
2. **saturation/entropy** — trung bình kênh S (HSV) + entropy màu. Photo cao,
   sơ đồ thường phẳng.
3. **flat_fraction** — tỉ lệ pixel thuộc top-K màu phổ biến nhất. Sơ đồ cao
   (ít màu nền), photo thấp (màu trải đều).
4. **line_density** — Canny + `HoughLinesP`, đếm đường thẳng dài chuẩn hoá.
   Sơ đồ/biểu đồ cao (trục, lưới, khung), photo thấp.
5. **whitespace_fraction** — tỉ lệ pixel gần trắng. Sơ đồ trên nền trắng cao.

Kết hợp thành điểm `diagram_score` vs `photo_score`; `confidence = |margin|`.
`margin` dưới một dải ngưỡng → `uncertain`. Hằng số ngưỡng tinh chỉnh ở plan
với ảnh tổng hợp có biên rõ ràng (gradient/nhiễu = photo; nét đen trên nền trắng
= diagram), nên ngưỡng có biên an toàn rộng.

**Interface AI (chưa dùng khi extract):** định nghĩa Protocol
`PictureVisionClassifier` với `classify(crop_bytes) -> "photo"|"diagram"`. #0 chỉ
khai báo; #2/#3 sẽ truyền một implementation Gemini. Khi không có classifier
(extract): figure `uncertain` giữ nguyên `uncertain` → trang thành `preserve`.

## C. Phát hiện cover

`detect_cover(page_index, total_pages, text_ratio, fig_ratio, bg_is_photo)
-> "front"|"back"|"none"` theo heuristic vị trí + tỉ lệ:
- `front` nếu `page_index == 0` và (`fig_ratio` đủ lớn hoặc `bg_is_photo`) và
  `text_ratio < cover_text_max`.
- `back` nếu `page_index == total_pages-1` và điều kiện tương tự.
- ngược lại `none`.

## D. Quyết định trang (thuần, test được)

`classify_page(text_ratio, fig_ratio, figure_labels, has_table, bg_is_photo)
-> "text"|"preserve"|"regenerable"`:
1. Nếu không có figure và không `bg_is_photo` và có chữ → `text`.
2. `preserve` nếu `has_table` HOẶC bất kỳ nhãn nào trong `figure_labels` thuộc
   `{diagram, uncertain}`.
3. `regenerable` nếu image-dominant/ít chữ VÀ có figure VÀ mọi nhãn == `photo`
   VÀ không `has_table`.
4. Ngược lại: nếu figure ít & có chữ → `text`; còn lại mặc định `preserve`.

`has_table` = có block role `table` (extractor đã gán role từ docling label).

## E. Mô hình dữ liệu & lắp ráp

- `PageModel` thêm `page_class: str = "text"`, `cover: str = "none"`; serialize
  trong `to_dict`/`from_dict` với default an toàn (model.json cũ vẫn nạp được).
  Không đổi schema DB (đi kèm trong `model_json` sẵn có).
- Module mới, mỗi file một trách nhiệm:
  - `app/services/picture_classifier.py` — heuristic `classify_picture` +
    Protocol `PictureVisionClassifier`. Thuần theo pixel.
  - `app/services/page_eligibility.py` — `classify_page` + `detect_cover`. Thuần.
- `extractor.py`: sau khi crop figures, với mỗi figure `picture` gọi
  `classify_picture`; tổng hợp `figure_labels`, tính `has_table`, gọi
  `classify_page` + `detect_cover`; gán vào PageModel.
- Endpoint metadata trang (`documents.py`, nhánh non-raw) trả thêm `page_class`,
  `cover` để frontend (và #3) hiển thị/ghi đè sau.

### Backfill (phục vụ test trên sách đã extract)

`relabel_document(doc_dir)` — duyệt các `*.model.json` + crop figure trên đĩa,
tính lại `page_class`/`cover` (heuristic-only) và ghi đè model.json. Cho phép
gắn nhãn lại tài liệu cũ mà không chạy lại toàn bộ extraction. Một script mỏng
gọi hàm này (không cần endpoint trong #0).

## F. Kiểm thử (TDD)

- `page_eligibility.classify_page`: table→preserve; figure diagram→preserve;
  toàn photo + ít chữ→regenerable; có figure uncertain→preserve; không figure +
  có chữ→text.
- `detect_cover`: trang đầu image-dominant ít chữ→front; trang cuối→back; giữa→none.
- `picture_classifier.classify_picture`: ảnh tổng hợp nét đen/nền trắng→diagram;
  ảnh gradient/nhiễu nhiều màu→photo; ảnh biên mờ→uncertain (margin nhỏ).
- `PageModel` round-trip: `to_dict`/`from_dict` giữ `page_class`/`cover`; nạp
  model.json cũ (thiếu field) → default `text`/`none`.

## G. Ngoài phạm vi #0

- Không inpaint, không sinh ảnh AI, không gọi Gemini lúc extract (đó là #1/#2/#3).
- Không có nút chất lượng UI (đó là #2).
- Không đổi schema DB. `text_fitter`/renderer L3 không đụng tới.

## Các file đụng tới

- Tạo: `app/services/picture_classifier.py`, `app/services/page_eligibility.py`,
  script backfill (vd `scripts/relabel_document.py` hoặc hàm trong service).
- Sửa: `app/services/page_model.py` (2 field), `app/services/extractor.py`
  (lắp ráp), router trả metadata (`documents.py`).
- Test: `tests/test_picture_classifier.py`, `tests/test_page_eligibility.py`,
  bổ sung `tests/test_page_model.py`.
