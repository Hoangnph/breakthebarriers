# Manual Per-Page Mode — Thiết kế

Ngày: 2026-06-05
Nhánh dự kiến: nhánh mới từ `main` (vd `feat/manual-per-page`)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

## Bối cảnh

Pipeline tự động (#0 classifier → CleanPage → AI cleaning) đôi khi sai (vd bìa bị
`preserve` nên không làm sạch được; trang chưa dịch). Cần một **panel thủ công
per-page** để người dùng tự ghi đè: ép kiểu nền, làm sạch/revert, dịch lại trang,
và sửa chữ dịch bằng cách **click thẳng vào chữ trên trang**.

Building blocks đã có:
- Dịch lại trang: `POST /api/docs/{id}/translate` (body có `page_num`).
- Sửa 1 span: `PUT /api/docs/{id}/translations/{span_id}`.
- Làm sạch nền: `POST .../pages/{n}/clean-bg?method=full|inpaint&force=`.
- Render: `GET .../pages/{n}?lang=&raw=`; `resolve_background_policy(page_class, cover)`
  điều khiển nền; `render_text_layer` phát `.tl-text` cho mỗi block.

Còn thiếu: **ép policy nền**, **revert ảnh sạch**, **click-to-edit chữ**.

## A. Ép kiểu nền thủ công (effective policy)

- Hàm thuần `effective_policy(page_class, cover, override) -> str`: nếu `override`
  ∈ {`base-color`,`keep-raster`,`clean-photo`} → trả `override`; ngược lại (None/lạ)
  → `resolve_background_policy(page_class, cover)`.
- Override lưu ở `model_json.background.policy_override` (mặc định không có = auto).
- **`render_text_layer` dùng `effective_policy(...)`** thay cho `resolve_background_policy`
  trực tiếp (đọc override từ `model.background`).
- **Gating clean-bg** (`documents.py`) cũng dùng `effective_policy` → ép `clean-photo`
  là làm cho endpoint chấp nhận làm sạch trang mà classifier gán sai.
- Endpoint `POST /api/docs/{id}/pages/{n}/policy` body `{"value": "auto"|"base-color"|"keep-raster"|"clean-photo"}`:
  `auto` → xóa `policy_override`; còn lại → set. Lưu `model_json`, trả `{policy_override}`.

## B. Revert ảnh đã làm sạch

- `POST /api/docs/{id}/pages/{n}/clean-bg/revert`: xóa `background.clean_image` khỏi
  `model_json` (GIỮ file `.clean*.png` trên đĩa làm cache). Renderer quay về raster gốc.
  Trả `{status: "reverted"}`. Nếu chưa có clean_image → vẫn 200 (idempotent).
- **Regenerate** = clean-bg sẵn có với `?force=true` (ghi đè cache).

## C. Click-to-edit chữ dịch (cross-iframe)

- `render_text_layer`: mỗi `<div class="tl-text">` thêm thuộc tính
  `data-span="{span_id}"`. Script render thêm handler: click một `.tl-text` →
  `window.parent.postMessage({type:"btb-edit", span_id, text}, "*")` (text =
  `el.textContent`). Handler luôn phát; **parent chỉ xử lý khi đang ở chế độ sửa**.
- Frontend (chế độ sửa bật trong panel): lắng nghe `message` `btb-edit` → mở ô nhập
  điền sẵn `text` → lưu → `PUT /api/docs/{id}/translations/{span_id}` `{translated_text}`
  → reload tab (cache-bust). Không bật sửa thì click không làm gì.

## D. Re-translate trang + sửa span (tái dùng)

- "Dịch lại trang" → `POST .../translate` với `page_num` (+ chất lượng nếu payload hỗ trợ).
- Sửa span đi qua luồng C (click-to-edit) → `PUT translations/{span_id}`.

## E. Frontend — Panel "Tùy chỉnh trang"

Panel gập/mở cạnh preview, theo trang hiện tại; đọc `page_class`/`cover`/`policy_override`/
có `clean_image` từ `GET pages/{n}` (non-raw, bổ sung trả các field này):
```
┌─ Tùy chỉnh trang {n} ─────────────────────────────┐
│ Nền:  (•)Auto ( )Trắng ( )Giữ ảnh ( )Làm sạch     │
│        [Làm sạch: Full] [Inpaint]   [Revert]      │
│ Dịch: [Dịch lại trang]  (chất lượng ▾)            │
│ Chữ:  [☑ Bật sửa chữ] → click vào chữ để sửa      │
└────────────────────────────────────────────────────┘
```
- Radio Nền → `POST policy` (auto/base-color/keep-raster/clean-photo) → reload.
- Nút Làm sạch/Revert bật khi effective policy = clean-photo.
- "Dịch lại trang" → `POST translate`; hiện trạng thái.
- "Bật sửa chữ" → bật listener `btb-edit`.

## Mở rộng API metadata

`GET /api/docs/{id}/pages/{n}` (non-raw) trả thêm `policy_override` và
`has_clean_image` (bool) để panel hiển thị đúng trạng thái.

## Kiểm thử (TDD, backend)

- `effective_policy`: override hợp lệ thắng; None→auto; override lạ→auto.
- `render_text_layer`: model có `background.policy_override="base-color"` (dù
  page_class=preserve) → KHÔNG vẽ raster; `policy_override="clean-photo"` →
  vẽ clean_image nếu có.
- Endpoint `policy`: set → `model_json.background.policy_override` đúng; `auto` → xóa.
- Endpoint `clean-bg/revert`: bỏ `clean_image` khỏi model_json; idempotent khi chưa có.
- Gating clean-bg dùng effective policy: trang preserve + override clean-photo →
  clean-bg KHÔNG 400 (mock cleaner).
- `render_text_layer` phát `data-span="{span_id}"` cho mỗi block + chứa `btb-edit`
  trong script.
- Metadata: `GET pages/{n}` trả `policy_override`, `has_clean_image`.

## Ngoài phạm vi

- Thao tác hàng loạt (apply cho dải trang) — để sau.
- Re-extract trang.
- Undo nhiều bước / lịch sử.

## Các file đụng tới

- Tạo: `app/services/effective_policy.py` (hoặc thêm vào `background_policy.py`).
- Sửa: `app/services/text_layer_renderer.py` (effective_policy + data-span + edit script),
  `app/routers/documents.py` (policy endpoint, revert endpoint, gating dùng effective,
  metadata thêm field).
- Frontend: panel "Tùy chỉnh trang" + listener btb-edit (`apps/break_the_barriers/frontend`).
- Test: `tests/test_effective_policy.py` (mới), bổ sung `tests/test_text_layer_renderer.py`,
  `tests/test_preview_pagemodel.py`.
