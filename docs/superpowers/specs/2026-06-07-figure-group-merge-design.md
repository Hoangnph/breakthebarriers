# Khôi phục cấu trúc nhóm ảnh (Figure-Group Layout) — Thiết kế

Ngày: 2026-06-07
Nhánh: `feat/figure-group-layout` (từ `main` sau khi merge document-flow)
Trạng thái: đã duyệt thiết kế (hybrid 2 phương án) — sẵn sàng viết plan

## Bối cảnh & vấn đề

Flow tách một **ảnh nhúng gốc** thành N figure rời (vd dải 3 chân dung Yann LeCun /
Geoffrey Hinton / Yoshua Bengio, p11) → sort theo y-top → **xếp dọc full-width**,
mất **bố cục hàng** và **caption baked** (tên là pixel trong ảnh, không phải text).

**Khảo sát toàn doc (11 nhóm figure cùng hàng)** chia 2 ca:
- **Ảnh-đơn-bị-tách** (union nằm trong 1 ảnh nhúng PDF): p1,p4,p5,p6,p11,p20,p34 —
  caption thường **baked** trong ảnh.
- **Lưới ảnh rời** (ngoài 1 ảnh PDF): p9 (2 ảnh thật cạnh nhau), p27/p28/p44 (lưới
  deepfake/icon) — caption thường là **text PDF** (vd s9–s22 ở p27).

## Nguyên tắc (hybrid — tự quyết theo toạ độ)

Mỗi **cụm figure** (gần nhau về không gian) được quyết định cách chuyển đổi từ toạ
độ + ảnh nhúng PDF:
- **merge-image**: cụm nằm trong MỘT ảnh nhúng PDF → vốn là một ảnh bị tách → **cắt
  lại một ảnh** từ raster theo bbox bao (+ dải caption baked). Giữ layout + caption
  baked, không OCR. Renderer KHÔNG đổi (là một `illustration`).
- **grid**: cụm là nhiều ảnh rời → **dựng lại lưới CSS theo toạ độ** (số cột/hàng suy
  từ x/y), mỗi ô = ảnh + caption text (giữ dịch được, responsive, không tràn).

## Thiết kế

### A. Phát hiện cụm (`figure_grouper.cluster_figures`, thuần hình học)
```python
def cluster_figures(figures) -> list[list[int]]   # các cụm (index figure), mỗi cụm >=2
```
- Hai figure "gần" nếu bbox **nới 30%** của chúng giao nhau (proximity). Gom cụm bắc
  cầu (transitive). Chỉ giữ cụm **≥2** figure.

### B. Quyết định phương án (extraction, có PDF)
`decide_mode(cluster_bbox, page_pdf_image_bboxes) -> "merge" | "grid"`:
- `"merge"` nếu tồn tại một ảnh nhúng PDF bao trùm `cluster_bbox` (sai số 2pt).
- ngược lại `"grid"`.

### C. merge-image (cắt 1 ảnh — `figure_grouper.merge_group_crop`)
- bbox gộp = union các thành viên, **mở rộng đáy** lấy caption baked: đáy mới =
  `min(top của block-text gần nhất nằm dưới & chồng x, union_bottom + 0.5*group_h)`
  − gap 2pt; nếu không có → `union_bottom + 0.35*group_h`.
- Crop raster trang theo bbox (scale `W/page_w`) → `{doc}-{page}-figgroup{n}.png`.
- Thay N thành viên bằng **một** `Figure(bbox, img=figgroup, kind="illustration")`.

### D. grid (CSS lưới theo toạ độ)
- Các thành viên giữ nguyên (không crop gộp) nhưng được gắn **`Figure.group_id`** chung
  + **`Figure.group_caption_spans`** (span_id các block-text nằm ngay dưới mỗi ảnh =
  caption của ảnh đó; gán theo "block dưới figure, chồng x nhiều nhất").
- `flow_model`: các figure cùng `group_id` → một `FlowElement(kind="figure_group")`
  mang: danh sách (figure src, caption span_id, cột, hàng). Số **cột** = số cụm x phân
  biệt (gom x-center gần nhau); **hàng** = số cụm y. Thứ tự ô theo (hàng, cột).
- `flow_renderer`: render `<div class="fl-figgrid" style="grid-template-columns:repeat(C,1fr)">`,
  mỗi ô `<figure><img><figcaption data-span></figcaption></figure>`. Caption tra
  translations như mọi text → **dịch được**. Responsive (1fr), không tràn.
- Caption span dùng cho group đã bị "nuốt" → KHÔNG flow lại như đoạn rời (thêm vào
  tập covered/consumed như cơ chế suppress hiện có).

### E. Wiring
- **Extraction** (`extractor.py`): sau khi crop figures + có raster + PDF image bboxes,
  `cluster_figures` → mỗi cụm `decide_mode`: `merge` → C (thay figure); `grid` → D (gắn
  group_id + caption spans).
- **Backfill** (`scripts/merge_figure_groups.py <doc_id> [--dry-run]`): doc đã extract
  — nạp PageModel + raster `background.image` + mở PDF gốc lấy image bboxes; áp dụng C/D;
  ghi `model_json`. (Dùng cho 2024-wttc.)

## Kế thừa & không đổi
- `classify_figure`, `_center_inside` tái dùng.
- merge-image: renderer KHÔNG đổi.
- Suppress baked-label hiện có vẫn đúng; caption-group (text) được gán group nên không
  flow rời.

## Kiểm thử (TDD)
- `cluster_figures`: 3 ảnh cùng hàng (gần) → 1 cụm 3; 2 ảnh xa nhau → không cụm; lưới
  2×2 gần nhau → 1 cụm 4.
- `decide_mode`: cluster trong 1 image bbox → "merge"; ngoài → "grid".
- `merge_group_crop`: raster giả, crop bbox → file đúng kích thước; mở rộng đáy đúng.
- `group_id`/grid trong `build_document_flow`: PageModel có figure group_id → một
  `figure_group` element với C cột đúng, caption spans gán đúng, member figures không
  còn flow rời.
- `flow_renderer`: figure_group → `<div class="fl-figgrid">` grid C cột, mỗi ô có
  `<img>` + `<figcaption data-span>`; caption dịch hiển thị; không có figure rời trùng.

## Ngoài phạm vi
- Khôi phục caption **baked thành text** (giữ nguyên dạng pixel qua crop).
- Vị trí pixel-tuyệt-đối trong grid (dùng lưới C×R suy từ toạ độ, không absolute).
- Cụm theo overlap phức tạp/ảnh chồng ảnh.

## Các file đụng tới
- Tạo: `app/services/figure_grouper.py` (`cluster_figures`, `decide_mode`, `merge_group_crop`,
  `assign_grid`).
- Sửa: `app/services/page_model.py` (`Figure.group_id`, `Figure.group_caption_spans`).
- Sửa: `app/services/flow_model.py` (build `figure_group` element từ group_id; suppress
  caption spans đã gán).
- Sửa: `app/services/flow_renderer.py` (render `figure_group` = CSS grid + `.fl-figgrid` CSS).
- Sửa: `app/services/extractor.py` (gọi cluster→decide→merge/grid).
- Tạo: `scripts/merge_figure_groups.py` (backfill).
- Test: `tests/test_figure_grouper.py`, bổ sung `tests/test_flow_model.py`,
  `tests/test_flow_renderer.py`.
