# Flow Polish (Sub-project B3) — Thiết kế

Ngày: 2026-06-09
Nhánh: `fix/layout-original-to-html`
Trạng thái: đã duyệt thiết kế

PDF kiểm chứng: `apps/break_the_barriers/assets/books/2024-wttc-introduction-to-ai.pdf`. Backend chạy `:8000`. Chrome headless để chụp kiểm chứng.

## Bối cảnh

Sau B2.2, `/flow` đã faithful + overlay dịch (đã kiểm chứng qua Chrome). B3 hoàn thiện 3 mảng còn lại (gộp 1 sub-project):
- **B3a NAV lai từ TOC** — yêu cầu gốc của người dùng ("sửa NAV theo TOC").
- **B3b Dọn mode UI** — bỏ mode `HTML(en)` reflow dư thừa.
- **B3c Tinh chỉnh mask** — khử ghost chữ gốc ở mép (thấy trên trang text dày).

Phát hiện nền:
- Số trang in trong TOC **khớp** chỉ số raster page (Algorithms=8→p8…), nhưng `toc_parser._TOC_RE` (yêu cầu leader 3+ chấm/tab) **bỏ sót** entry chỉ có khoảng trắng + số → NAV phải dùng parser nới lỏng (chỉ trên trang đã xác nhận TOC) + map theo heading (bỏ qua sai số).

## Thiết kế

### B3a — NAV lai từ TOC

Module `app/services/toc_parser.py` (mở rộng) — thuần:
- `extract_toc_entries(block_texts) -> List[Tuple[str, str | None]]`: trên danh sách text (theo thứ tự block của trang TOC), nhận entry với leader **nới lỏng** (`\.{2,}` | `…+` | `\t` | `\s{2,}`) + số cuối; trả `(title, num)` giữ thứ tự. (Chỉ gọi khi `is_toc_page` đúng → nới lỏng an toàn.)
- `map_entry_to_page(title, page_headings, printed_num=None) -> int | None`: chuẩn hoá (`[^a-z0-9]+`→space, lower) rồi khớp `title` với heading từng trang (`page_headings = List[(page_num, heading_text)]`): bằng / prefix hai chiều → trả `page_num`. Không khớp → fallback `int(printed_num)` nếu hợp lệ; else None.

Endpoint `/flow` (`documents.py`):
- Tìm trang TOC: trang đầu tiên có `is_toc_page` trên **original_text** các block.
- `entries = extract_toc_entries(original texts của trang TOC theo thứ tự block)`; song song giữ map `original_title -> translated label` (parse loose trên translated text cùng block; fallback title gốc).
- `page_headings`: với mọi trang, lấy `(page_num, original_text)` của block `role=="heading"`.
- Dựng `nav = [(label, target)]` với `target = map_entry_to_page(title, page_headings, num)`, bỏ entry `target is None`.
- Truyền `nav` (mặc định None) vào `render_faithful_flow`.

`faithful_flow_renderer.render_faithful_flow(pages, translations, image_url_base, nav=None)`:
- Khi `nav`: render `<details class="ff-nav" open><summary>Mục lục</summary>…<a href="#pg-{target}">label</a>…</details>` ở **đầu** `ff-doc` (trước các trang). CSS `.ff-nav`. Link cuộn trong iframe đến `#pg-{n}` (section đã có `id="pg-{n}"`).
- `nav=None` → không render (tương thích test cũ + trang không TOC).

### B3b — Dọn mode UI (frontend `app/books/[id]/preview/page.tsx`)
- Bỏ nút **HTML**; toggle còn **Gốc / Dịch**. `type Lang = "pdf" | "vi"` (bỏ `"en"`).
- `flowLang(l)`: `pdf → "en"` (flow Gốc = raster + overlay chữ gốc = bản gốc faithful), `vi → "vi"`. (Flow không có PDF toàn-tài-liệu nên Gốc trong flow = `en`.)
- Per-page (reader/sidebar/split): Gốc→`pdf` (PDF thật) như cũ, Dịch→`vi`.
- Validate localStorage: chấp nhận `["pdf","vi"]`; giá trị cũ `"en"` → coerce `"pdf"`.
- Nút Gốc disable ở flow? Không — flow Gốc hợp lệ (en). Giữ Gốc/Dịch bật ở mọi view; per-page Gốc=pdf, flow Gốc=en (qua flowLang).

### B3c — Tinh chỉnh mask (`text_layer_renderer._mask_css`)
- Thêm `box-shadow:0 0 0 3px {opaque_fill}` vào CSS mask → nới vùng phủ ~3px quanh hộp, che phần chữ gốc tràn mép. `overflow:hidden` của div không cắt box-shadow (chỉ cắt content). Áp dụng cho cả per-page (text_layer) lẫn flow (đều dùng `_mask_css`).

## Tái dùng / không đổi
- `render_faithful_page`, `resolve_page_raster`, fit cqw — không đổi (chỉ nhận mask mạnh hơn qua `_mask_css`).
- Backend extraction — không đổi.

## Đơn vị

| Unit | Vai trò | Test |
|------|---------|------|
| `extract_toc_entries(texts)` | parse TOC nới lỏng, giữ thứ tự | unit |
| `map_entry_to_page(title, headings, num)` | map title→page (heading match + fallback) | unit |
| `render_faithful_flow(..., nav=)` | render khối nav đầu flow | unit |
| `/flow` endpoint (dựng nav) | tích hợp | integration |
| `_mask_css` (box-shadow) | khử ghost mép | unit |
| `page.tsx` mode toggle | Gốc/Dịch | kiểm chứng thủ công |

## Kiểm thử & kiểm chứng

- **Unit:** `extract_toc_entries(["Algorithms : The Brains of AI    8","FOREWORD....3","Body text no number"])` → `[("Algorithms : The Brains of AI","8"),("FOREWORD","3")]`. `map_entry_to_page("Algorithms : The Brains of AI",[(8,"ALGORITHMS : THE BRAINS OF AI")])==8`; không khớp + num="12" → 12; rỗng → None. `render_faithful_flow(...,nav=[("Mục A",8)])` → có `<details class="ff-nav"` + `href="#pg-8"`+ "Mục A"; `nav=None` → không. `_mask_css` → chứa `box-shadow:0 0 0 3px`.
- **Integration `/flow`:** seed doc có trang TOC (entries) + heading trang khác → response chứa `ff-nav` + link `#pg-{n}` đúng.
- **Kiểm chứng (Chrome):** chụp flow WTTC: nav hiện đầu, click cuộn đúng trang; mép trang text dày hết ghost; frontend toggle Gốc/Dịch (mode HTML biến mất).

## Ngoài phạm vi
- Inpaint AI (mask hiện = hộp + box-shadow, đủ cho phần lớn). Sidebar nav React/scrollspy (nav in-document là đủ).

## Rủi ro & giảm thiểu
- **Parse TOC nới lỏng over-match** → chỉ chạy khi `is_toc_page` đúng; map theo heading lọc tiếp (entry không khớp + số trang lạ → vẫn fallback số, có thể trỏ sai trang hiếm — chấp nhận, đa số khớp heading).
- **box-shadow chồng giữa các block sát nhau** → 3px nhỏ, cùng màu nền → không lộ rõ.
- **Đổi `Lang` type bỏ `"en"`** → coerce giá trị localStorage cũ; flow vẫn dùng `en` nội bộ qua `flowLang`.
- **`render_faithful_flow` thêm tham số `nav`** → mặc định None, test cũ vẫn xanh.
