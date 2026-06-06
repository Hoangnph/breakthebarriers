# F3 — Frontend Flow View (mặc định) — Thiết kế

Ngày: 2026-06-07
Nhánh: tiếp tục `feat/document-flow` (sau F1+F2)
Trạng thái: đã duyệt thiết kế (sẵn sàng viết plan)

Sub-project **F3/4** (sau F1 flow model+renderer · F2 section+nav đồng bộ · trước F4 per-section translate).

## Bối cảnh & nguyên tắc

F1+F2 cho endpoint `GET /api/docs/{id}/flow?lang=en|vi` trả về **một tài liệu HTML cuộn dọc** đầy đủ: cover/figure → mục lục sinh tự động (in-document, anchor `#sec-{id}`) → các section. Khoá dịch + anchor đã **toàn cục** (`p{page}-{span}`) nên không đụng nhau giữa các trang.

Frontend hiện tại (`app/books/[id]/preview/`) hiển thị **từng trang** qua iframe (`/api/docs/{id}/pages/{n}?raw=true`), 3 layout (reader/sidebar/split) + controls per-page. Theo chiến lược "Flow là chính", F3 đưa **flow thành view mặc định**; chế độ per-page trở thành phụ (để sửa/căn chỉnh).

**Nguyên tắc:** tái dùng tối đa pattern iframe sẵn có; điều hướng dựa vào **mục lục in-document** (F2) — KHÔNG dựng sidebar ToC/scrollspy ở React (để F-sau nếu cần). Render qua **iframe** (cô lập CSS, an toàn).

## Thiết kế

### A. Mode toggle (preview/page.tsx)
- Thêm state `mode: "flow" | "page"`, lưu `localStorage["btb_preview_mode"]`, **mặc định `"flow"`** (kể cả khi chưa có giá trị lưu).
- Toggle ở header: **[≡ Liền mạch | ▭ Trang]** (icon `ScrollText` / `FileText` của lucide).
- **Flow mode** render `<LayoutFlow>`; **Page mode** giữ nguyên 3 layout + toàn bộ hành vi hiện tại (không đổi).

### B. Hiển thị/ẩn theo mode (header)
- **Flow mode — ẩn:** layout switcher (reader/sidebar/split), panel "Tùy chỉnh trang", nút clean-bg, page counter, nút lang **"Gốc"**.
- **Flow mode — giữ:** nút lang **HTML (en)** / **Dịch (vi)**; **zoom** (xem D).
- Lang coercion: helper thuần `flowLang(lang) -> "en" | "vi"` — nếu `lang === "pdf"` trả `"vi"`, ngược lại trả nguyên `lang`. Dùng cho src iframe ở flow mode.
- **Page mode:** mọi thứ như cũ (Gốc/HTML/Dịch, layout switcher, panel, zoom, counter).

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
- localStorage prefs (`btb_preview_layout`, `btb_preview_lang`) — thêm `btb_preview_mode` cùng kiểu.

## Kiểm thử
Repo frontend **không có test runner** (`package.json` chỉ `dev/build/start/lint`). F3 verify:
- **Backend (pytest):** thêm test cho `render_flow_html` — output chứa `<script>` zoom + chuỗi `btb-zoom` + đặt `fontSize`. (Các test flow hiện có vẫn xanh.)
- **Frontend:** `npx tsc --noEmit` (typecheck) + `npm run lint` sạch.
- **Thủ công (controller):** mở `/books/{id}/preview` → mặc định Flow; toggle Trang↔Liền mạch; đổi HTML/Dịch (iframe reload đúng lang); click mục lục → cuộn tới section; nút zoom đổi cỡ chữ. Chrome headless screenshot flow mặc định + sau zoom. KHÔNG dựng vitest mới (YAGNI).

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
