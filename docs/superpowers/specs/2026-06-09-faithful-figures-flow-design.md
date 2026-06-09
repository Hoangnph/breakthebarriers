# Faithful Figures in Flow (Sub-project A) — Thiết kế

Ngày: 2026-06-09
Nhánh: `fix/layout-original-to-html`
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

PDF kiểm chứng: `apps/break_the_barriers/assets/books/2024-wttc-introduction-to-ai.pdf`
Doc mẫu đã extract sẵn: `data/extracted_html/2024-wttc-introduction-to-ai/` (44 trang, có `*.model.json` + `page-{n}.png`).

## Bối cảnh

Đường render original → HTML hiện hành cho view mặc định là **flow** (`GET /api/docs/{id}/flow`):
`flow_model.build_document_flow(pages) → flow_renderer.render_flow_html(flow, translations, image_base)`.

Người dùng báo 4 nhóm lỗi layout. Sau phân tích, chia làm 2 vùng code khác nhau và 2 sub-project:

- **Sub-project A (tài liệu này):** lỗi liên quan figure — không đụng pipeline dịch.
- **Sub-project B (sau):** inline bold/italic (#2) — chạm `typography_extractor` + `translator_v2` + renderer.

### Triệu chứng thuộc A và gốc rễ

| # | Triệu chứng | Gốc rễ |
|---|---|---|
| 1 | Một số hình ảnh bị mất | Trang thiết kế nhiều chữ bị **reflow** thành (text + figure rời) → đồ hoạ không-phải-figure mất; figure docling không nhận diện → biến mất. (Ảnh figure đã được serve OK qua `/assets/{file}`, KHÔNG phải lỗi 404.) |
| 3 | Ảnh căn giữa bị mất căn giữa | `Figure` không có field `align`; `flow_renderer` render `<figure><img class="fl-fig">` mặc định canh trái. Lề có thể suy ra từ bbox (vd p7 `[158,53,282x273]` trên trang rộng 595 → lề trái 158 ≈ lề phải 155 = center). |
| 4 | Ảnh hội thoại AI vỡ layout | Vùng thiết kế (cụm icon/avatar `31x31` + text xen kẽ, vd p26–28) bị phân rã thành nhiều `<figure>` rời + text reflow → mất quan hệ không gian (avatar cạnh bóng chat). `figure_grouper` hiện chỉ merge cụm **toàn ảnh**, không kích hoạt khi cụm có text. |

**Nguyên tắc thiết kế:** đẩy phần nặng về **extraction + backfill** (giống `figure_grouper` đã có), giữ `flow_model` thuần và `flow_renderer` thay đổi tối thiểu → giảm rủi ro ở đường render live. Không đụng `.env`, không đụng pipeline dịch.

## Thiết kế

### 1. Căn lề figure (#3)

- Thêm field `align: str = "left"` vào dataclass `Figure` (`page_model.py`) — cập nhật `to_dict`/`from_dict` (đọc `f.get("align", "left")` để tương thích model.json cũ).
- Thêm field `align: str = "left"` vào `FlowElement` (`flow_model.py`).
- Helper thuần `infer_figure_align(bbox, page_w, tol_frac=0.08) -> str` (đặt trong `design_region.py` hoặc `flow_model.py`):
  - `left_margin = bbox[0]`, `right_margin = page_w - (bbox[0] + bbox[2])`.
  - `center` nếu `abs(left_margin - right_margin) <= tol_frac * page_w` **và** cả hai lề > 0.
  - `right` nếu `left_margin` lớn hơn `right_margin` rõ rệt (left > 2× right, right nhỏ).
  - else `left`.
- Set `align` cho mỗi `Figure` tại extraction; **backfill** tính cho doc cũ. `build_document_flow` truyền `align` xuống `FlowElement(kind="figure", ..., align=...)`.
- `flow_renderer`: render `<figure style="text-align:{align}">`, ảnh đổi sang `display:inline-block` (CSS `.fl-fig`) để `text-align` có hiệu lực căn giữa/phải. Banner overlay không đổi.

### 2. Phát hiện & crop vùng thiết kế (#1 + #4)

Module mới `app/services/design_region.py`:

- `@dataclass Region`: `bbox: List[float]` (điểm, l/t/w/h hợp nhất), `block_ids: set[str]` (span_id block thành viên), `figure_idx: set[int]` (index figure thành viên).
- `detect_design_regions(page: PageModel) -> List[Region]` — **thuần** (chỉ đọc PageModel, không I/O):
  - Xác định icon-figure: cả hai chiều `< _ICON_MAX_FRAC * page` (tái dùng ngưỡng `0.15` từ `flow_model`).
  - Cluster theo proximity (tái dùng/điều chỉnh `figure_grouper.cluster_figures`) trên icon-figure + figure nhỏ lân cận.
  - **Trigger (bảo thủ, sẽ tinh chỉnh trên p26–28):** một cluster đủ điều kiện "vùng thiết kế" khi: có **≥2 figure** và **≥1 text block** có tâm nằm trong dải dọc của cluster (text xen giữa các icon) — tức bố cục phi tuyến. Guard chống nuốt text thường: bỏ qua nếu cluster chỉ là 1 figure + text liền mạch một cột.
  - Region bbox = hợp nhất bbox của figure thành viên + block thành viên, cộng `pad` (~6pt). `block_ids` = các block có tâm trong region bbox; `figure_idx` = figure thành viên.
- Crop & ghi (tại extraction/backfill, KHÔNG trong `detect_*`): với mỗi region, crop bbox (đổi pt→px theo tỉ lệ `page-{n}.png`) bằng helper crop sẵn có (`figure_grouper.crop_group_region` hoặc PIL) → `{doc}-{n}-regionK.png`. Tái dùng cơ chế pt→px của `figure_grouper`.
- Cập nhật PageModel: thêm `Figure(bbox=region.bbox, img="{doc}-{n}-regionK.png", kind="content-region", align="center")`; **gỡ** figure thành viên (theo `figure_idx`) và block thành viên (theo `block_ids`) khỏi `page.figures`/`page.blocks` (đã bake vào crop). Lưu `model.json` + cột `DBPage.model_json`.
- `flow_model` không cần logic mới cho region: figure `content-region` được phát như figure thường (đã có nhánh `kind="figure"`), đã canh giữa qua `align`.

### 3. Guard "không bao giờ mất figure" (#1)

- Test bất biến trên doc mẫu: mọi `Figure` trong PageModel xuất hiện trong flow (đếm `kind in ("figure","image_block")` + overlay banner + region) — trừ banner-consumed và region-consumed.
- `flow_renderer`: `<img alt="figure">` giữ nguyên; nếu cần, thêm fallback text nhẹ (không bắt buộc) — ưu tiên đảm bảo URL đúng.

### 4. Backfill script

- `scripts/backfill_design_regions.py` (mẫu theo backfill figure-group đã có, commit `0f8adfa`):
  - Duyệt 1 doc: đọc từng `model.json` + `page-{n}.png`, áp dụng `infer_figure_align` cho mọi figure, chạy `detect_design_regions` + crop + cập nhật model, ghi lại `model.json` và `DBPage.model_json`.
  - Idempotent: bỏ qua figure đã là `content-region` region-crop (theo tên `-regionK.png`).
  - Chạy cho `2024-wttc-introduction-to-ai` để kiểm chứng.

## Đơn vị (isolation)

| Unit | Vai trò | Phụ thuộc | Test |
|------|---------|-----------|------|
| `infer_figure_align` | suy align từ bbox | thuần | unit |
| `Region` + `detect_design_regions` | phát hiện vùng thiết kế | PageModel (thuần) | unit (fixtures p7/p26-28) |
| crop region | pt→px + cắt ảnh | PIL + page raster | integration |
| `flow_model` (align passthrough) | gắn align vào FlowElement | design_region | unit |
| `flow_renderer` (align CSS) | render căn lề | — | unit (snapshot) |
| backfill script | áp dụng cho doc cũ | DB + I/O | chạy tay trên doc mẫu |

## Kiểm thử & kiểm chứng

- **Unit (SQLite/thuần):** `infer_figure_align` (left/center/right), `detect_design_regions` (p26-28 → có region; trang text thường → rỗng), `flow_renderer` alignment, guard không-mất-figure.
- **Integration / kiểm chứng thủ công:** chạy backfill trên `2024-wttc-introduction-to-ai`, mở `/api/docs/{id}/flow`:
  - p7: ảnh căn giữa.
  - p26–28: hội thoại AI hiển thị thành 1 ảnh crop liền mạch (không vỡ avatar/bóng chat).
  - Không trang nào mất figure so với bản gốc.
- Re-extract từ PDF kiểm chứng (`assets/books/2024-wttc-introduction-to-ai.pdf`) nếu cần đối chiếu đường extraction (không chỉ backfill).

## Ngoài phạm vi

- Inline bold/italic (#2) → **Sub-project B** (spec riêng).
- Export PDF/EPUB (SP-B cũ).
- Thay đổi pipeline dịch / `.env`.

## Rủi ro & giảm thiểu

- **Trigger region quá rộng** (nuốt text dịch được) → bắt đầu bảo thủ (≥2 figure + text xen kẽ), validate trên p26-28, có guard 1-figure-một-cột.
- **Crop sai tỉ lệ pt→px** → tái dùng cơ chế đã kiểm chứng của `figure_grouper`.
- **model.json cũ thiếu `align`** → `from_dict` default `"left"`, backfill bổ sung.
