# SP5 Document Preview — Design Spec

**Goal:** Thêm trang `/books/[id]/preview` cho phép owner xem nội dung từng trang của tài liệu đã extract/dịch, với 3 layout chuyển đổi linh hoạt.

---

## 1. Architecture

### Route & Auth

- **URL:** `/books/[id]/preview`
- **Auth:** Tự động protected qua middleware (`/books/:path*` đã có trong matcher). Chỉ owner mới truy cập được (backend trả 403 nếu không phải owner).
- **Component type:** Client Component (`"use client"`) — cần state động cho layout, toggle, navigation.

### Backend APIs (đã có, không cần thêm)

| Endpoint | Mô tả | Dùng khi |
|----------|-------|----------|
| `GET /api/docs/{id}/pages` | Danh sách trang: `{page_num, status, has_original, has_translated}` | Mount lần đầu |
| `GET /api/docs/{id}/pages/{page_num}?lang=en` | Original HTML (JSON) | Reader/Sidebar view |
| `GET /api/docs/{id}/pages/{page_num}?lang=vi` | Translated HTML (JSON) | Reader/Sidebar view |
| `GET /api/docs/{id}/pages/{page_num}?lang=en&raw=true` | Full HTML document | iframe trong Split view |
| `GET /api/docs/{id}/pages/{page_num}?lang=vi&raw=true` | Full HTML document | iframe trong Split view |

### File Structure

| File | Trách nhiệm |
|------|-------------|
| `frontend/app/books/[id]/preview/page.tsx` (NEW) | Main page — state, fetching, layout router |
| `frontend/app/books/[id]/preview/LayoutReader.tsx` (NEW) | Layout A: full-width reader |
| `frontend/app/books/[id]/preview/LayoutSidebar.tsx` (NEW) | Layout B: sidebar + main view |
| `frontend/app/books/[id]/preview/LayoutSplit.tsx` (NEW) | Layout C: split view 2 iframes |

---

## 2. Header (sticky, shared across all layouts)

```
[← Pipeline]  daoduckinhlaotu.pdf          [Original | Translated]  [☰ ⊞ ⬜⬜]  [3/33]
```

- **Back link:** `← Pipeline` → `/books/[id]`
- **Toggle Original/Translated:** 2-button group. Disabled "Translated" nếu trang chưa dịch (`has_translated = false`).
- **Layout switcher:** 3 icon buttons — Reader (☰), Sidebar (⊞), Split (⬜⬜). Active button highlight indigo.
- **Page counter:** `{currentPage}/{totalPages}` — update khi navigate.
- **State persistence:** Layout + toggle lưu vào `localStorage` key `btb_preview_layout` và `btb_preview_lang`. Khôi phục khi mở lại.

---

## 3. Layout A — Reader (default)

**Mô tả:** Full-width single column. Nội dung trang render bằng `dangerouslySetInnerHTML`. Bottom nav prev/next.

```
┌─────────────────────────────────┐
│  [sticky header]                │
├─────────────────────────────────┤
│                                 │
│   <article HTML content>        │
│   prose max-w-3xl mx-auto       │
│                                 │
├─────────────────────────────────┤
│  [← Trang 2]      [Trang 4 →]  │
└─────────────────────────────────┘
```

- Fetch `GET /api/docs/{id}/pages/{page}?lang={en|vi}` → render `html` field.
- Loading state: skeleton placeholder.
- Scroll to top khi đổi trang.
- Prev/next links với page number labels.

---

## 4. Layout B — Sidebar

**Mô tả:** Left panel (240px fixed) danh sách tất cả trang. Click để jump. Right panel nội dung trang đang chọn.

```
┌──────────┬──────────────────────┐
│ Trang 1  │                      │
│ Trang 2  │  <article HTML>      │
│ ▶Trang 3 │   prose content      │
│ Trang 4  │                      │
│ Trang 5  │                      │
│   ...    │                      │
└──────────┴──────────────────────┘
```

- Sidebar item hiển thị: page number + badge trạng thái (`✓` dịch xong, `○` chưa dịch, `—` chưa extract).
- Active page highlight trong sidebar, auto-scroll sidebar item vào view.
- Right panel: cùng render logic như Layout A.
- Sidebar collapsible trên mobile (hidden, toggle button).

---

## 5. Layout C — Split View

**Mô tả:** 2 cột song song — trái Original, phải Translated. Dùng `<iframe>` với `src` trỏ đến endpoint `?raw=true`.

```
┌──────────────────┬───────────────────┐
│   ORIGINAL       │   TRANSLATED      │
│                  │                   │
│  <iframe         │  <iframe          │
│   ?lang=en       │   ?lang=vi        │
│   &raw=true>     │   &raw=true>      │
│                  │                   │
└──────────────────┴───────────────────┘
         [← Trang trước] [Trang sau →]
```

- Token được append vào iframe src (`?token={localStorage.btb_token}`) vì iframe không gửi cookie auth tự động — backend cần hỗ trợ query param `token` (đã có từ SSE endpoint).
- Nếu trang chưa dịch: iframe bên phải hiển thị message "Trang này chưa được dịch" (HTML inline).
- Iframe height: fixed `calc(100vh - 120px)` — không cần postMessage resize cho MVP.
- Toggle Original/Translated trong header bị ẩn ở Split view (vì cả 2 đã hiện).

---

## 6. Data Flow

```
mount
  → GET /api/docs/{id}          (lấy filename, total_pages, status)
  → GET /api/docs/{id}/pages    (lấy page list với has_original, has_translated)
  → render layout với page 1

page change / lang change
  → Layout A/B: GET /api/docs/{id}/pages/{n}?lang={en|vi}  → setHtml
  → Layout C:   đổi iframe src (browser tự fetch)

layout switch
  → setLayout (state), lưu localStorage
  → re-render layout component, giữ nguyên currentPage
```

---

## 7. Error Handling

- API lỗi → hiển thị error banner, không crash toàn trang.
- `has_translated = false` + user chọn Translated → show message "Trang này chưa được dịch" thay vì blank.
- Trang không có `original_html` → show "Đang chờ extract".
- Document không tồn tại (404) → redirect về `/dashboard`.

---

## 8. Navigation từ Pipeline

Trong `/books/[id]/page.tsx` (pipeline page), thêm button **"Xem nội dung"** (icon `FileText`) cạnh các action button hiện tại, visible khi `doc.status !== "raw"` (tức là đã có ít nhất extracted pages).

---

## 9. Testing

Không cần backend test mới (API đã có tests). Frontend: build passes cleanly là đủ cho MVP. Manual test:
- [ ] Mở 3 layout, verify render đúng
- [ ] Toggle Original/Translated
- [ ] Navigate trang prev/next
- [ ] Layout + lang preference persist sau reload
- [ ] Split view iframes load đúng cả 2 cột
- [ ] "Chưa dịch" state hiển thị đúng

---

## Self-Review Notes

- **No new API needed** — `GET /api/docs/{id}/pages` và `GET /api/docs/{id}/pages/{page_num}` đã có đầy đủ.
- **Token in iframe src** — Split view cần token vì iframe không mang cookie. Pattern này đã dùng ở SSE endpoint.
- **Scope:** 4 files mới + 1 file sửa (pipeline page thêm button). Không chạm backend.
- **Auth enforcement:** Middleware đã protect `/books/*` — không cần thêm check phía frontend.
- **YAGNI:** Không thêm re-translate từng trang, comment, highlight, search trong trang — chỉ view.
