# Khôi phục cấu trúc nhóm ảnh (Figure-Group Merge) — Thiết kế

Ngày: 2026-06-07
Nhánh: `feat/figure-group-layout` (từ `main` sau khi merge document-flow)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

## Bối cảnh & vấn đề

Trong flow, một **ảnh nhúng gốc** (vd dải 3 chân dung Yann LeCun / Geoffrey Hinton /
Yoshua Bengio trên page 11) bị extraction **cắt thành N figure rời** (3 face-crop
91×100). Hậu quả: flow sort theo y-top → N mảnh **xếp dọc full-width**, mất:
- **bố cục hàng** (3 cột → 3 ảnh dọc);
- **caption baked** (tên nằm trong dải pixel y253–285 của ảnh gốc, KHÔNG phải text
  PDF; bị cắt khỏi các face-crop nên mất hẳn).

**Khảo sát toàn doc 2024-wttc** (11 nhóm figure cùng hàng):
- **7 nhóm** = một ảnh nhúng PDF bị tách (p1,p4,p5,p6,p11,p20,p34) — kind
  `illustration`, union nằm trong 1 ảnh PDF. Đây là ca "mất cấu trúc" chính.
- **1 nhóm** = hàng ảnh thật, 2 ảnh riêng cạnh nhau (p9).
- **3 nhóm** = lưới hỗn hợp icon + content-region (p27,p28,p44) — KHÔNG xử lý.

## Nguyên tắc & insight

Các face-crop vốn là **một ảnh**. Cách trung thực & đơn giản nhất: **đừng tách** —
gộp các figure cùng hàng lại thành **một ảnh** bằng cách **cắt lại từ raster trang**
theo bbox bao của nhóm (mở rộng xuống để lấy dải caption baked). Vì là một ảnh
raster, nó **tự giữ cả bố cục hàng lẫn tên baked**, không cần OCR, không cần CSS
grid. Áp dụng đồng nhất cho cả "ảnh-đơn-bị-tách" và "hàng ảnh thật" (crop union bao
gồm cả 2 ảnh + khoảng giữa). **Renderer KHÔNG đổi** — figure gộp là `illustration`,
render full-width như mọi figure.

## Thiết kế

### A. Phát hiện nhóm (`flow_model.group_same_row_figures`, thuần hình học)
```python
def group_same_row_figures(figures, page_w, page_h, blocks) -> list[dict]:
    # mỗi nhóm: {"members": [Figure...], "bbox": [x0,y0,w,h]}  (bbox đã mở rộng caption)
```
- Chỉ xét figure `classify_figure(...) == "illustration"` (bỏ banner/icon/content-region).
- **Cùng hàng**: hai figure cùng hàng nếu khoảng chồng theo trục y `> 0.5 * min(h)`.
  Gom cụm bắc cầu (transitive) các figure cùng hàng.
- Nhóm hợp lệ = **≥ 2** figure illustration cùng hàng.
- **bbox nhóm** = union bbox các thành viên, **mở rộng đáy xuống** để lấy caption
  baked: đáy mới = `min(top của block-text gần nhất nằm dưới nhóm và chồng x với
  nhóm, union_bottom + 0.5*group_h)`, trừ một gap nhỏ (2pt). Nếu không có block nào
  bên dưới trong tầm → `union_bottom + 0.35*group_h`. (Giữ caption baked, không nuốt
  đoạn text kế tiếp.)

### B. Tạo figure gộp (extraction + backfill — cắt raster)
`figure_grouper.merge_group_crop(page_raster_path, bbox, page_w, page_h, out_path)`:
- Mở raster trang, scale `sx=W/page_w, sy=H/page_h`, crop vùng `bbox` (pixel), lưu
  `out_path`. Trả `True`/`False`.
- Tên file gộp: `{doc}-{page}-figgroup{n}.png`.
- Thay N figure thành viên bằng **một** `Figure(bbox=bbox, img=figgroup, kind="illustration")`.

### C. Wiring
- **Extraction** (`extractor.py`): sau khi dựng danh sách `figures` (đã crop từng cái)
  và có `page_image` raster, gọi `group_same_row_figures`; với mỗi nhóm crop gộp từ
  raster, thay thành viên bằng figure gộp. (Guard: cần có raster trang.)
- **Backfill** (`scripts/merge_figure_groups.py <doc_id> [--dry-run]`): cho doc đã
  extract — nạp PageModel + raster `background.image` từ đĩa, gộp, ghi `model_json`.
  Dùng cho doc 2024-wttc hiện có.

## Kế thừa & không đổi
- `classify_figure`, `_center_inside` (flow_model) tái dùng.
- **Renderer (`flow_renderer`) KHÔNG đổi**: figure gộp render full-width như illustration.
- Suppress baked-label vẫn đúng: caption nhóm (vd "Media nicknamed…", là text PDF nằm
  NGOÀI bbox gộp) vẫn flow như caption dưới ảnh.

## Kiểm thử (TDD)
- `group_same_row_figures`:
  - 3 illustration cùng y (3 cột) → 1 nhóm 3 thành viên; bbox = union mở rộng đáy.
  - 2 figure khác hàng (y rời) → không nhóm.
  - nhóm có 1 icon + 1 illustration → không nhóm (chỉ illustration).
  - mở rộng đáy: có block text dưới nhóm → đáy dừng trên block đó; không có → +0.35*h.
- `merge_group_crop`: tạo raster giả (vd 600×800, vùng màu), crop bbox → file out đúng
  kích thước vùng (theo scale).
- Extraction/backfill: PageModel có nhóm → sau xử lý còn 1 figure gộp thay N (test bằng
  raster tạm + model giả, guard PYTEST cho phần AI không liên quan).

## Ngoài phạm vi
- Lưới hỗn hợp icon/content-region (p27/p28/p44).
- CSS grid nhiều cột cho ảnh rời (đã thay bằng crop-gộp một ảnh).
- Khôi phục caption dạng **text** (ở đây caption là pixel baked → đã giữ qua crop).
- Nhóm theo cột dọc (chỉ xử lý cùng-hàng).

## Các file đụng tới
- Sửa: `app/services/flow_model.py` (`group_same_row_figures`).
- Tạo: `app/services/figure_grouper.py` (`merge_group_crop`).
- Sửa: `app/services/extractor.py` (gọi gộp sau khi crop figures).
- Tạo: `scripts/merge_figure_groups.py` (backfill).
- Test: `tests/test_flow_model.py` (group), `tests/test_figure_grouper.py` (crop),
  bổ sung extraction/backfill test.
