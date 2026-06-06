# 3b — Cấu trúc mục lục (TOC) — Thiết kế

Ngày: 2026-06-06
Nhánh dự kiến: tiếp tục `feat/manual-per-page`
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

Việc **#3b** (cuối trong nhóm hậu-verify). #3a (text-no-loss) đã xong.

## Bối cảnh & vấn đề

Trang mục lục (trang 2) mỗi mục là **"Tiêu đề [chấm dẫn HOẶC tab] số trang"**:
- s4/s12: `LỜI NÓI ĐẦU..............3` (chấm literal trong chữ)
- s6–s11: `Thuật toán : Bộ não của AI⇥ 8` (TAB + số)

Chữ dịch dài + chấm literal → dòng rất rộng → wrap nhiều dòng → **đè nhau**, chấm
dẫn/số trang vỡ. Mục tiêu: **chấm dẫn CSS + số trang căn phải + không đè**.

Các block khác trên trang (s3 "MỤC LỤC" heading, s1 header, s2 footer) KHÔNG phải
mục TOC.

## Quyết định đã chốt

- **Chỉ áp dụng trên trang TOC** (nhận diện trang là mục lục trước → an toàn).
- Phát hiện theo **mẫu leader** (≥3 chấm hoặc tab) + số cuối; trang TOC = có ≥3
  block khớp.
- Dựng lại ở **render-time** (theo ngôn ngữ; không đổi extraction).

## Thành phần thuần (test được)

### A. `toc_parser.py` (mới)
```python
parse_toc_entry(text: str) -> tuple[str, str] | None
```
- Regex tách `(title, page_num)`: tiêu đề (non-greedy), rồi **leader** = `\.{3,}`
  (≥3 chấm ASCII) HOẶC `…+` (ellipsis) HOẶC `\t`, rồi `[\s.…]*`, rồi
  `\d+` ở cuối (+ khoảng trắng cuối).
- Trả `(title.strip(), num)`; **None** nếu không khớp (câu thường, không số cuối,
  không leader) → tránh false-positive.

```python
is_toc_page(block_texts: list[str], *, min_entries: int = 3) -> bool
```
- Đếm số phần tử mà `parse_toc_entry` khớp; True nếu `>= min_entries`.
- Không cần nhận diện chữ "Contents/Mục lục" theo ngôn ngữ.

### B. Renderer (`text_layer_renderer.py`)
- Trước vòng block: `toc_page = is_toc_page([translations.get(b.span_id, "") for b in model.blocks])`.
- Trong vòng: nếu `toc_page` và `parse_toc_entry(text)` khớp → emit **cấu trúc TOC
  flex**; ngược lại emit `tl-text` thường (như hiện tại).
- Block khớp giữ nguyên định vị absolute (left/top/width/min-height/max-height) +
  font + role-fit (#3a), nhưng nội dung là flex 3 phần thay vì text-có-chấm-literal.

Cấu trúc TOC (thêm class, vẫn là div absolute):
```html
<div class="tl-text tl-toc" data-fit="1" data-span="…" style="…absolute+font…">
  <span class="tl-toc-title">{title}</span>
  <span class="tl-toc-leader"></span>
  <span class="tl-toc-num">{num}</span>
</div>
```

### C. CSS (`_CSS`)
```css
.tl-toc { display: flex; align-items: flex-end; gap: 0; white-space: nowrap; }
.tl-toc-title { flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; }
.tl-toc-leader { flex: 1 1 8px; min-width: 8px; margin: 0 4px 3px;
                 border-bottom: 1px dotted currentColor; }
.tl-toc-num { flex: 0 0 auto; }
```
- Chấm dẫn = `border-bottom: dotted` của span co giãn (flex:1). Số trang `flex:0 0`
  → luôn nằm phải. Tiêu đề 1 dòng (nowrap), ellipsis nếu quá dài (hiếm với TOC).
- **Bỏ chấm literal** trong chữ ⇒ dòng không còn rộng bất thường ⇒ hết wrap/đè.
- `.tl-toc` vẫn nằm trong `.tl-text` (kế thừa `overflow:hidden` + fit). Vì là 1
  dòng (nowrap) nên chiều cao = 1 dòng → fit #3a giữ gọn.

## Kiểm thử (TDD)

- `parse_toc_entry`:
  - `"Tiêu đề......3"` → `("Tiêu đề", "3")`
  - `"Thuật toán : Bộ não của AI\t 8"` → `("Thuật toán : Bộ não của AI", "8")`
  - `"...trong năm 2023."` (kết bằng số nhưng không leader) → `None`
  - `"MỤC LỤC"` (không số) → `None`
  - `"FOREWORD…… 4"` (ellipsis char) → `("FOREWORD", "4")`
- `is_toc_page`: list có ≥3 mục khớp → True; list body thường → False.
- `render_text_layer`:
  - Trang TOC (≥3 mục khớp): block mục lục có `class="tl-toc"` + `tl-toc-title`
    chứa title + `tl-toc-num` chứa số; KHÔNG còn chuỗi chấm literal trong HTML;
    heading "MỤC LỤC" (không khớp) vẫn `tl-text` thường (không có `tl-toc`).
  - Trang non-TOC (0–1 mục khớp): KHÔNG có `tl-toc` (an toàn, không đụng).

## Ngoài phạm vi

- TOC nhiều cấp lồng (chỉ xử 1 cấp "tiêu đề … số").
- Số trang dạng "iv"/"A-1" (chỉ số nguyên).
- Căn chỉnh thụt lề theo cấp mục.

## Các file đụng tới

- Tạo: `app/services/toc_parser.py`.
- Sửa: `app/services/text_layer_renderer.py` (CSS + nhánh render TOC).
- Test: `tests/test_toc_parser.py` (mới), bổ sung `tests/test_text_layer_renderer.py`.
