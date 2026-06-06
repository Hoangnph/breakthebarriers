# F2 — Sections + Synced Contents Nav — Thiết kế

Ngày: 2026-06-06
Nhánh: tiếp tục `feat/document-flow` (sau F1)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

Sub-project **F2/4** (sau F1 flow model+renderer · trước F3 frontend · F4 per-section translate).

## Bối cảnh & nguyên tắc

F1 cho một tài liệu flow phẳng (heading/đoạn/figure/image_block). F2 thêm **cấu
trúc section + điều hướng (mục lục) đồng bộ**. Yêu cầu production quan trọng:
**mục lục hiển thị KHÔNG được lệch với điều hướng thật.**

**Nguyên tắc: một nguồn sự thật (single source of truth).** Cấu trúc = các
**heading thật** trong flow. Mục lục/Contents được **sinh từ chính các heading
đó** → không thể lệch; mỗi mục là **link tới anchor section**. Trang mục lục gốc
(OCR, hay bị gộp/bẩn) bị **thay** bằng mục lục sinh tự động này.

## Thiết kế (trong `flow_renderer`)

### A. Section + anchor
- Duyệt flow: mỗi `heading` mở `<section id="sec-{span_id}">` (đóng section trước);
  nội dung theo sau nằm trong section đó. Element trước heading đầu → một
  `<section>` "intro" không tiêu đề.
- `id` = `sec-{span_id}` (span_id duy nhất → anchor ổn định).

### B. Mục lục sinh tự động (đồng bộ + click)
- Thu thập **headings** (render-time, có translations): `(id, level, text_dịch)`.
- Sinh khối Contents: `<nav class="fl-contents">` chứa mỗi heading thành
  `<a href="#sec-{id}" class="fl-toc-link lvl{level}"><span class="t">{text}</span><span class="fl-toc-dots"></span></a>` (chấm dẫn CSS, thụt theo level). **Không số trang** — dùng anchor.
- **Vị trí:** chèn ngay tại **mục TOC gốc đầu tiên** (element mà `parse_toc_entry`
  khớp). Đồng thời **bỏ render mọi element TOC gốc** (parse_toc_entry khớp) →
  thay bằng khối Contents sinh. Nếu tài liệu KHÔNG có trang TOC (không element nào
  khớp) → không chèn Contents in-flow (điều hướng luôn-hiện là việc F3).
- Vì Contents và (sau này) nav F3 đều sinh từ cùng tập headings → **0 lệch**.

### C. CSS (`_CSS` của flow_renderer)
```css
.fl-doc section { scroll-margin-top: 16px; }
.fl-contents { margin: 1.5em 0; padding: 0; }
.fl-toc-link { display: flex; align-items: flex-end; text-decoration: none;
               color: inherit; margin: .25em 0; }
.fl-toc-link .t { flex: 0 1 auto; }
.fl-toc-dots { flex: 1 1 8px; min-width: 8px; margin: 0 4px 4px;
               border-bottom: 1px dotted #aaa; }
.fl-toc-link.lvl2 { margin-left: 1.5em; }
.fl-toc-link.lvl3 { margin-left: 3em; }
.fl-toc-link:hover .t { text-decoration: underline; }
```

## Kế thừa
- `flow_model` (F1) giữ nguyên (heading + level đã có).
- `toc_parser.parse_toc_entry` (#3b) tái dùng để **nhận diện + bỏ** element TOC gốc.
- Anchor + Contents thuần render-time; không đổi DB/extraction.

## Kiểm thử (TDD)
- Section: flow 2 heading + đoạn → mỗi heading bọc `<section id="sec-{span}">`;
  element trước heading đầu → section "intro" (không id heading).
- Contents sinh: flow có ≥1 heading + một số element-TOC-gốc → HTML có
  `<nav class="fl-contents">` với link `href="#sec-{id}"` cho TỪNG heading; text
  link = chữ dịch của heading; thụt `.lvl{n}` đúng.
- Suppress + thay: element TOC gốc (parse_toc_entry khớp) KHÔNG render văn bản
  thô (không còn chấm literal của nó); Contents sinh nằm ở vị trí TOC gốc đầu tiên.
- Không TOC page: flow không element nào khớp parse_toc_entry → KHÔNG có
  `fl-contents`, nhưng section vẫn có anchor.
- Anchor↔link khớp: mọi `href="#sec-X"` trong Contents đều có `<section id="sec-X">` tương ứng (0 lệch).

## Ngoài phạm vi F2
- Sidebar sticky / scrollspy / nav luôn-hiện (F3 frontend).
- Khớp-tên TOC gốc ↔ heading (đã loại — dùng single-source thay thế).
- Mục lục đa cấp lồng `<ul>` sâu (dùng danh sách phẳng thụt theo level).

## Các file đụng tới
- Sửa: `app/services/flow_renderer.py` (section wrap + heading collect + Contents sinh + suppress TOC gốc + CSS). Import `parse_toc_entry` từ `toc_parser`.
- Test: bổ sung `tests/test_flow_renderer.py`.
