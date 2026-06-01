# SP6 Per-page Translation — Design Spec

**Goal:** Cho phép dịch từng trang riêng lẻ với lựa chọn ngôn ngữ đích, theo dõi trạng thái dịch từng trang và toàn bộ tài liệu real-time.

---

## 1. Architecture

**Không cần thêm backend** — endpoints đã đủ:
- `POST /api/docs/{id}/translate` — dịch 1 trang (`page_num`, `target_lang`, `background=true`)
- `POST /api/docs/{id}/translate-all` — dịch tất cả (`target_lang`)
- `GET /api/docs/{id}/pages` — list pages với `{page_num, status, has_original, has_translated}`

**Thay đổi duy nhất:** `apps/break_the_barriers/frontend/app/books/[id]/page.tsx` (MOD)

---

## 2. Language Selector

Dropdown 7 ngôn ngữ đặt trong header, cạnh nút "Dịch tất cả". Lưu vào `localStorage` key `btb_translate_lang` để nhớ lựa chọn.

| Code | Label |
|------|-------|
| `vi` | 🇻🇳 Tiếng Việt |
| `en` | 🇺🇸 English |
| `zh` | 🇨🇳 中文 |
| `ja` | 🇯🇵 日本語 |
| `ko` | 🇰🇷 한국어 |
| `fr` | 🇫🇷 Français |
| `de` | 🇩🇪 Deutsch |

---

## 3. Page List Panel

Hiển thị khi `doc.status !== "raw"` (sau extract). Danh sách tất cả trang với:

| Cột | Nội dung |
|-----|---------|
| Trang | Số trang |
| Trạng thái | Badge màu (xem bên dưới) |
| Hành động | Button tùy trạng thái |

**Badge trạng thái:**
- `raw` → ○ xám — "Chưa dịch" + button **[Dịch trang này]**
- `translating` → ● xanh lam pulse — "Đang dịch..." + button disabled **[—]**
- `translated` → ✓ xanh lá — "Đã dịch" + button **[Dịch lại]**
- `compiled` → ✓✓ tím — "Đã compile" + button **[Dịch lại]**
- `failed` → ✗ đỏ — "Lỗi" + button **[Thử lại]**

**Document-level status** (pipeline stepper hiện tại) tự cập nhật khi tất cả trang đã dịch.

---

## 4. Per-page Translation Action

Khi nhấn **[Dịch trang này]** / **[Dịch lại]** / **[Thử lại]**:

1. Set page status locally → `translating` (optimistic UI)
2. Gọi `POST /api/docs/{id}/translate` với `{ page_num, target_lang, background: true }`
3. Polling `GET /api/docs/{id}/pages` mỗi 3s khi có ít nhất 1 trang đang `translating`
4. Khi trang hoàn thành → badge cập nhật, polling dừng nếu không còn trang nào `translating`

---

## 5. "Dịch tất cả" Update

Thay `target_lang: "vi"` hardcode bằng `target_lang` từ state (language selector). Behavior giữ nguyên — gọi `POST /api/docs/{id}/translate-all` + SSE progress stream.

---

## 6. UI Layout

```
┌──────────────────────────────────────────────────┐
│ ← daoduckinh.pdf                                 │
├──────────────────────────────────────────────────┤
│  Pipeline: Upload ✓ → Extract ✓ → Dịch … → ○   │
├──────────────────────────────────────────────────┤
│  [🌐 Tiếng Việt ▼]  [▶ Dịch tất cả]  [👁 Xem]  │
├──────────────────────────────────────────────────┤
│  # Trang │ Trạng thái        │ Hành động         │
│  ────────┼───────────────────┼─────────────────  │
│  1       │ ✓ Đã dịch         │ [Dịch lại]        │
│  2       │ ✓ Đã dịch         │ [Dịch lại]        │
│  3       │ ● Đang dịch...    │ [—]               │
│  4       │ ○ Chưa dịch       │ [Dịch trang này]  │
│  5       │ ✗ Lỗi             │ [Thử lại]         │
│  ...     │                   │                   │
└──────────────────────────────────────────────────┘
```

Language selector + Dịch tất cả nằm cùng hàng, phía trên page list. Page list chỉ hiện khi doc đã extract xong.

---

## 7. Polling Strategy

- **Bắt đầu poll** khi: có ít nhất 1 trang status = `translating`
- **Interval:** 3 giây
- **Dừng poll** khi: không còn trang nào `translating`
- **Cleanup:** `clearInterval` khi component unmount
- Polling dùng `GET /api/docs/{id}/pages` — không cần endpoint mới

---

## 8. Scope & Constraints

- **1 file thay đổi:** chỉ `frontend/app/books/[id]/page.tsx`
- **Không thay đổi backend** — translate endpoint đã có `target_lang`
- **Không thêm language selector cho published books** — SP3 reader dùng lang toggle riêng
- **Quality tier** không expose trong UI — dùng mặc định "high" của backend

---

## Self-Review

- ✅ Không có placeholder/TBD
- ✅ Polling dừng đúng khi xong, cleanup khi unmount
- ✅ Language lưu localStorage — không mất khi reload
- ✅ Optimistic UI (set `translating` ngay) → UX mượt
- ✅ Translate-all vẫn dùng SSE (không đổi flow)
- ✅ 1 file duy nhất — không tạo component mới (page.tsx đã lớn nhưng thêm vào hợp lý)
