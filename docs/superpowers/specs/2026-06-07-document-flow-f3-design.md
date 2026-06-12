# F3 — Frontend Flow View (mặc định) — Thiết kế

Ngày: 2026-06-07
Nhánh: tiếp tục `feat/document-flow` (sau F1+F2)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

Sub-project **F3/4** (sau F1 flow model+renderer · F2 section+nav đồng bộ · trước F4 per-section translate).

## Bối cảnh & nguyên tắc

F1+F2 cho endpoint `GET /api/docs/{id}/flow?lang=en|vi` trả về **một tài liệu HTML cuộn dọc** đầy đủ: cover/figure → mục lục sinh tự động (in-document, anchor `#sec-{id}`) → các section. Khoá dịch + anchor đã **toàn cục** (`p{page}-{span}`) nên không đụng nhau giữa các trang.

Frontend hiện tại (`app/books/[id]/preview/`) hiển thị **từng trang** qua iframe (`/api/docs/{id}/pages/{n}?raw=true`), 3 layout (reader/sidebar/split) + controls per-page. Theo chiến lược "Flow là chính", F3 đưa **flow thành view mặc định**; chế độ per-page trở thành phụ (để sửa/căn chỉnh).

**Nguyên tắc:** tái dùng tối đa pattern iframe sẵn có; điều hướng dựa vào **mục lục in-document** (F2) — KHÔNG dựng sidebar ToC/scrollspy ở React (để F-sau nếu cần). Render qua **iframe** (cô lập CSS, an toàn). **UX đồng nhất: tối đa hoá việc dùng CHUNG các nút giữa các view** — Flow chỉ là một lựa chọn xem nữa, không phải một "thế giới UI" tách biệt.

## Thiết kế

### A. Gộp Flow vào BỘ CHUYỂN VIEW duy nhất (preview/page.tsx)
Thay vì thêm một toggle mode tách rời, **mở rộng chính `layout switcher` hiện có** thành 4 lựa chọn — một control duy nhất điều phối "cách xem tài liệu":

`[≡ Liền mạch] [▤ Reader] [▦ Sidebar] [▥ Split]`

- Kiểu mở rộng: `type Layout = "flow" | "reader" | "sidebar" | "split"`. Tái dùng key cũ `localStorage["btb_preview_layout"]`, **mặc định `"flow"`** (kể cả khi chưa lưu, hoặc giá trị lưu không hợp lệ). **Không** thêm key `btb_preview_mode` riêng.
- Icon: `ScrollText` (Liền mạch) + `AlignJustify`/`LayoutTemplate`/`Columns2` (3 layout cũ), cùng một nhóm nút bo góc như hiện tại → Flow là nút đầu, được chọn mặc định.
- `layout === "flow"` → render `<LayoutFlow>`; còn lại giữ nguyên Reader/Sidebar/Split (không đổi hành vi).

### B. Các nút DÙNG CHUNG ở mọi view (đồng nhất)
Giữ **cùng một control, cùng vị trí** ở tất cả view; chỉ đổi trạng thái enable/disable theo ngữ cảnh — không ẩn/hiện gây "nhảy" layout:
- **Lang toggle 3 nút Gốc/HTML/Dịch:** hiện ở MỌI view (kể cả flow). Ở flow, nút **"Gốc"** bị **disable** (mờ, không click — vì flow không có PDF toàn-tài-liệu), y như nút **"Dịch"** đang disable khi trang chưa có bản dịch. Khi đang chọn `pdf` mà chuyển sang flow → tự nhảy về `vi` (qua `flowLang`).
- **Zoom controls:** hiện ở MỌI view; flow phản hồi qua zoom cỡ chữ (xem D).
- **Back / filename:** như cũ, mọi view.
- Helper thuần `flowLang(lang) -> "en" | "vi"`: `pdf → vi`, còn lại giữ nguyên. Dùng cho src iframe flow.

### B2. Các nút THEO NGỮ CẢNH (công cụ sửa từng trang)
Những thứ sau là **công cụ chỉnh sửa per-page** (gắn với một trang đang focus), nên chỉ hiện ở các layout per-page (`reader|sidebar|split`), ẩn ở flow — đây là *đúng ngữ cảnh*, không phải bất nhất (F4 sẽ mang sửa-trên-flow):
- Page counter `{currentPage}/{total}` → ở flow đổi thành chỉ tổng số: `{total} trang` (vẫn hiện thông tin, không để trống).
- Nút clean-bg (Full/Inpaint/Revert) — phụ thuộc policy của trang hiện tại.
- Panel "Tùy chỉnh trang" (radio nền, Dịch lại trang, Bật sửa chữ).

### C. LayoutFlow.tsx (mới)
```tsx
interface FlowLayoutProps { docId: string; apiUrl: string; lang: "en" | "vi"; zoom: number }
```
- Full-height, cuộn dọc. `src = ${apiUrl}/api/docs/${docId}/flow?lang=${lang}`.
- `<iframe key={lang} sandbox="allow-same-origin allow-scripts" className="w-full h-full border-none block"
   onLoad={(e)=> e.currentTarget.contentWindow?.postMessage({type:"btb-zoom", zoom}, "*")} />`.
- Đổi `lang` → `key` đổi → iframe reload `/flow?lang=`. Mục lục in-document lo điều hướng (anchor cuộn nội bộ iframe).

### D. Zoom cỡ chữ trong flow (render_flow_html + LayoutFlow)
- `render_flow_html` thêm một `<script>` nhỏ (trước `</body>`): nghe `message` `btb-zoom` → đặt `document.documentElement.style.fontSize = (zoom*100)+"%"`. Vì flow dùng `rem` cho cỡ chữ (h1=2rem…) nên scale root font-size = zoom chữ; px layout (max-width, padding) giữ nguyên — hợp lý cho "đọc to/nhỏ".
- LayoutFlow `onLoad` gửi zoom hiện tại; effect broadcast zoom sẵn có ở `preview/page.tsx` (`querySelectorAll("iframe")…postMessage`) tiếp tục hoạt động cho iframe flow.
- Nút zoom hiện cả ở flow mode.

## Kế thừa
- Endpoint `/flow` (F1/F2) + khoá toàn cục `p{page}-{span}` (fix vừa rồi) — không đổi backend ngoài đoạn `<script>` zoom.
- Pattern iframe + `key` reload + postMessage zoom — y như `LayoutReader`.
- localStorage prefs: **tái dùng `btb_preview_layout`** (mở rộng nhận thêm `"flow"`, default `"flow"`); `btb_preview_lang` giữ nguyên. KHÔNG thêm key mới.

## Kiểm thử
Repo frontend **không có test runner** (`package.json` chỉ `dev/build/start/lint`). F3 verify:
- **Backend (pytest):** thêm test cho `render_flow_html` — output chứa `<script>` zoom + chuỗi `btb-zoom` + đặt `fontSize`. (Các test flow hiện có vẫn xanh.)
- **Frontend:** `npx tsc --noEmit` (typecheck) + `npm run lint` sạch.
- **Thủ công (controller):** mở `/books/{id}/preview` → mặc định **Liền mạch**; chuyển qua lại Liền mạch/Reader/Sidebar/Split trong cùng một bộ switcher; ở flow xác nhận nút **"Gốc" bị disable**, HTML/Dịch reload iframe đúng lang; click mục lục → cuộn tới section; nút zoom đổi cỡ chữ; xác nhận các công cụ per-page (clean-bg/panel) ẩn ở flow và hiện lại khi sang Reader. Chrome headless screenshot flow mặc định + sau zoom. KHÔNG dựng vitest mới (YAGNI).

## Ngoài phạm vi F3
- Sidebar ToC dính + scrollspy (đã chốt dựa vào nav in-document; để sau nếu cần).
- Per-section AI translate / manual edit trên flow (F4).
- "Gốc" (PDF) cho cả tài liệu ở flow mode (per-page mới có PDF từng trang).
- Đồng bộ vị trí cuộn flow ↔ currentPage giữa hai mode.

## Các file đụng tới
- Tạo: `app/books/[id]/preview/LayoutFlow.tsx`.
- Sửa: `app/books/[id]/preview/page.tsx` (mode state + toggle + ẩn/hiện theo mode + flowLang + truyền props LayoutFlow).
- Sửa: `backend/app/services/flow_renderer.py` (đoạn `<script>` zoom).
- Test: `backend/tests/test_flow_renderer.py` (bổ sung test script zoom).
