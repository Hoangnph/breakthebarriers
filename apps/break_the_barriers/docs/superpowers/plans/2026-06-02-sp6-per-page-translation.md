# SP6 Per-page Translation (V2 + Pipeline & Preview) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép dịch từng trang riêng lẻ bằng engine V2 (glossary + context), chọn ngôn ngữ đích, theo dõi trạng thái từng trang real-time — ở cả trang Pipeline lẫn Preview.

**Architecture:** Thêm cờ `use_v2` cho endpoint dịch-1-trang để chạy `TranslatorV2.translate_page_batch` (load context từ `documents.ai_metadata` + glossary từ `document_glossaries`). Frontend: trang Pipeline thêm language selector + page list + nút per-page + polling; Preview thêm nút "Dịch trang này" trong sidebar. Trạng thái lấy từ `GET /api/docs/{id}/pages`.

**Tech Stack:** FastAPI, SQLAlchemy, TranslatorV2 (google.genai), Next.js 14 (React), Tailwind, pytest.

**Lệnh test backend (cwd = `apps/break_the_barriers/backend`):** `.venv/bin/pytest`
**Lệnh typecheck frontend (cwd = `apps/break_the_barriers/frontend`):** `npx tsc --noEmit`

---

## File Structure

| File | Trách nhiệm | Tạo/Sửa |
|------|-------------|---------|
| `backend/app/models.py` | `TranslationRequest` thêm `use_v2: bool = True` | Sửa |
| `backend/app/routers/translation.py` | Helper load context+glossary; V2 single-page path trong `translate_page` | Sửa |
| `backend/tests/test_api.py` | Test V2 single-page (sync + async) + V1 fallback | Sửa |
| `frontend/app/books/[id]/page.tsx` | Language selector + page list + per-page translate + polling | Sửa |
| `frontend/app/books/[id]/preview/page.tsx` | State target lang + poll khi đang dịch | Sửa |
| `frontend/app/books/[id]/preview/LayoutSidebar.tsx` | Nút "Dịch trang này" mỗi trang | Sửa |

**7 ngôn ngữ** (dùng chung cả Pipeline lẫn Preview), hằng số đặt inline tại mỗi nơi dùng:
`vi`🇻🇳, `en`🇺🇸, `zh`🇨🇳, `ja`🇯🇵, `ko`🇰🇷, `fr`🇫🇷, `de`🇩🇪.

---

## Task 1: Backend — V2 single-page translation

**Files:**
- Modify: `backend/app/models.py` (`TranslationRequest` ~line 16)
- Modify: `backend/app/routers/translation.py` (`translate_page` ~line 77; add helpers near top)
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Add `use_v2` to the request model**

Trong `backend/app/models.py`, class `TranslationRequest`:
```python
class TranslationRequest(BaseModel):
    page_num: int
    target_lang: str = "vi"
    quality_tier: str = "high"
    use_v2: bool = True
```

- [ ] **Step 2: Write failing tests** — append to `backend/tests/test_api.py`

```python
def test_translate_page_v2_sync(client):
    # V2 single-page (default use_v2=True) returns a translated result synchronously.
    client.post("/api/docs/clean_code/extract")
    resp = client.post("/api/docs/clean_code/translate",
                       json={"page_num": 1, "target_lang": "vi"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "translated"
    assert data["page_num"] == 1


def test_translate_page_v2_async_marks_translating(client, db_session):
    from backend.app.models_db import DBPage
    client.post("/api/docs/clean_code/extract")
    resp = client.post("/api/docs/clean_code/translate?async_mode=true",
                       json={"page_num": 2, "target_lang": "vi", "use_v2": True})
    assert resp.status_code == 202
    assert resp.json()["status"] == "translating"
    # background task runs synchronously under TestClient → page ends translated
    page = db_session.query(DBPage).filter(
        DBPage.document_id == "clean_code", DBPage.page_num == 2).first()
    assert page.status in ("translated", "translating")


def test_translate_page_v1_still_supported(client):
    client.post("/api/docs/clean_code/extract")
    resp = client.post("/api/docs/clean_code/translate",
                       json={"page_num": 1, "target_lang": "vi", "use_v2": False})
    assert resp.status_code == 200
    assert resp.json()["status"] == "translated"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api.py -k "translate_page_v2 or translate_page_v1" -v`
Expected: the V2 tests behave like V1 currently (may pass by coincidence on sync) OR fail; the async test FAILS because there is no V2 async path yet. The goal is the new behavior below.

- [ ] **Step 4: Add a context/glossary loader helper**

Trong `backend/app/routers/translation.py`, thêm hàm (sau các import, trước `translate_page`):
```python
def _load_context_and_glossary(doc, target_lang: str, db: Session):
    """Load V2 document context (ai_metadata JSON) + glossary entries for a target lang."""
    try:
        context = _json.loads(doc.ai_metadata or "{}")
    except Exception:
        context = {"title": doc.filename, "domain": "general", "style": "formal_academic"}
    rows = db.query(DBDocumentGlossary).filter(
        DBDocumentGlossary.document_id == doc.id,
        DBDocumentGlossary.target_lang == target_lang,
    ).all()
    glossary = [{"source": g.source_term, "target": g.target_term} for g in rows]
    return context, glossary


def _perform_v2_page(doc_id: str, page_num: int, target_lang: str,
                     context: dict, glossary: list, db: Session, quality: str) -> dict:
    """Translate a single page with TranslatorV2. Returns {status, page_num}."""
    return TranslatorV2.translate_page_batch(
        doc_id=doc_id, page_num=page_num, target_lang=target_lang,
        context=context, glossary=glossary, db=db, quality=quality,
    )


def run_v2_single_page(doc_id: str, page_num: int, target_lang: str, quality: str):
    """Background V2 single-page translation with its own DB session."""
    db = get_background_db()
    try:
        doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
        if not doc:
            return
        context, glossary = _load_context_and_glossary(doc, target_lang, db)
        _perform_v2_page(doc_id, page_num, target_lang, context, glossary, db, quality)
    except Exception as e:
        logger.error(f"V2 single-page translate failed for {doc_id} p{page_num}: {e}")
        try:
            pg = db.query(DBPage).filter(
                DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
            if pg:
                pg.status = "failed"
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
```

- [ ] **Step 5: Branch `translate_page` on `use_v2`**

Trong `backend/app/routers/translation.py`, thay phần thân `translate_page` SAU đoạn lấy `quality`:
```python
    quality = getattr(payload, "quality_tier", "high") or "high"
    use_v2 = getattr(payload, "use_v2", True)

    if use_v2:
        if async_mode:
            page.status = "translating"
            db.commit()
            if background_tasks:
                background_tasks.add_task(run_v2_single_page, doc_id, payload.page_num,
                                          payload.target_lang, quality)
            else:
                run_v2_single_page(doc_id, payload.page_num, payload.target_lang, quality)
            return JSONResponse(status_code=202, content={
                "status": "translating", "doc_id": doc_id,
                "page_num": payload.page_num, "message": "Translation started in background"
            })
        context, glossary = _load_context_and_glossary(doc, payload.target_lang, db)
        return _perform_v2_page(doc_id, payload.page_num, payload.target_lang,
                                context, glossary, db, quality)

    # V1 fallback (use_v2=False)
    if async_mode:
        page.status = "translating"
        db.commit()
        if background_tasks:
            background_tasks.add_task(run_background_translate, doc_id, payload.page_num,
                                      payload.target_lang, quality)
        else:
            run_background_translate(doc_id, payload.page_num, payload.target_lang, quality)
        return JSONResponse(status_code=202, content={
            "status": "translating", "doc_id": doc_id,
            "page_num": payload.page_num, "message": "Translation started in background"
        })
    return _perform_translation(doc_id, payload.page_num, payload.target_lang, db, quality)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api.py -k "translate_page" -v`
Expected: PASS — `test_translate_page` (existing), `test_translate_page_v2_sync`, `test_translate_page_v2_async_marks_translating`, `test_translate_page_v1_still_supported`.

- [ ] **Step 7: Run full suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all pass (the existing `test_translate_page` now routes through V2 sync, which returns `{status:"translated"}` via the pytest mock — assertion unchanged).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models.py backend/app/routers/translation.py backend/tests/test_api.py
git commit -m "feat(sp6): V2 single-page translation endpoint (use_v2 flag + context/glossary)"
```

---

## Task 2: Frontend Pipeline — language selector + page list + per-page translate

**Files:**
- Modify: `frontend/app/books/[id]/page.tsx`

Context: the page already has `doc`, `progress`, SSE streaming, `handleExtract`, `handleTranslateAll` (hardcodes `target_lang:"vi"` at ~line 113), and action buttons (~line 191-214). It does NOT list pages. `fetchAPI` is imported from `@/lib/api`.

- [ ] **Step 1: Add language constant + state**

Near the top of `frontend/app/books/[id]/page.tsx` (after imports), add:
```tsx
const LANGS = [
  { code: "vi", label: "🇻🇳 Tiếng Việt" },
  { code: "en", label: "🇺🇸 English" },
  { code: "zh", label: "🇨🇳 中文" },
  { code: "ja", label: "🇯🇵 日本語" },
  { code: "ko", label: "🇰🇷 한국어" },
  { code: "fr", label: "🇫🇷 Français" },
  { code: "de", label: "🇩🇪 Deutsch" },
] as const

const TRANSLATE_LANG_KEY = "btb_translate_lang"

interface PageRow {
  page_num: number
  status: string
  has_original: boolean
  has_translated: boolean
}
```
Inside the component, add state:
```tsx
const [targetLang, setTargetLang] = useState("vi")
const [pageRows, setPageRows] = useState<PageRow[]>([])
const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
```
Restore the saved lang on mount (add to the existing mount `useEffect` or a new one):
```tsx
useEffect(() => {
  const saved = localStorage.getItem(TRANSLATE_LANG_KEY)
  if (saved && LANGS.some((l) => l.code === saved)) setTargetLang(saved)
}, [])
```

- [ ] **Step 2: Add page-list loader + polling**

Add these functions inside the component:
```tsx
async function loadPages() {
  try {
    const rows = await fetchAPI<PageRow[]>(`/api/docs/${id}/pages`)
    setPageRows(rows)
    const anyTranslating = rows.some((r) => r.status === "translating")
    if (anyTranslating && !pollRef.current) {
      pollRef.current = setInterval(loadPages, 3000)
    } else if (!anyTranslating && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  } catch {
    // ignore — list is best-effort
  }
}

useEffect(() => {
  if (doc && doc.status !== "raw") loadPages()
  return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [doc?.status])
```

- [ ] **Step 3: Per-page translate handler**

```tsx
async function translateOnePage(pageNum: number) {
  setPageRows((rows) => rows.map((r) =>
    r.page_num === pageNum ? { ...r, status: "translating" } : r))
  try {
    await fetchAPI(`/api/docs/${id}/translate?async_mode=true`, {
      method: "POST",
      body: JSON.stringify({ page_num: pageNum, target_lang: targetLang, use_v2: true }),
    })
  } catch {
    setPageRows((rows) => rows.map((r) =>
      r.page_num === pageNum ? { ...r, status: "failed" } : r))
    return
  }
  if (!pollRef.current) pollRef.current = setInterval(loadPages, 3000)
}

function changeTargetLang(code: string) {
  setTargetLang(code)
  localStorage.setItem(TRANSLATE_LANG_KEY, code)
}
```

- [ ] **Step 4: Use selected lang in translate-all**

Change the existing `handleTranslateAll` body from `JSON.stringify({ target_lang: "vi" })` to:
```tsx
        body: JSON.stringify({ target_lang: targetLang }),
```

- [ ] **Step 5: Render language selector + page list**

After the action buttons block (the `doc.status !== "raw"` "Xem nội dung" button, ~line 214), and only when `doc.status !== "raw"`, add a language selector next to the actions and a page-list table. Add this JSX inside the render, after the existing actions row:
```tsx
{doc.status !== "raw" && (
  <div className="mt-6">
    <div className="flex items-center gap-3 mb-3">
      <label className="text-xs text-gray-500">Ngôn ngữ dịch</label>
      <select value={targetLang} onChange={(e) => changeTargetLang(e.target.value)}
              className="text-sm border border-gray-200 rounded-md px-2 py-1 bg-white">
        {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
      </select>
    </div>
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {pageRows.map((r) => {
        const translating = r.status === "translating"
        const done = r.has_translated || r.status === "translated" || r.status === "compiled"
        const failed = r.status === "failed"
        const label = translating ? "—"
          : done ? "Dịch lại" : failed ? "Thử lại" : "Dịch trang này"
        return (
          <div key={r.page_num}
               className="flex items-center justify-between px-4 py-2 border-b border-gray-100 last:border-b-0 text-sm">
            <span className="text-gray-700">Trang {r.page_num}</span>
            <span className={translating ? "text-blue-600" : done ? "text-green-600" : failed ? "text-red-600" : "text-gray-400"}>
              {translating ? "● Đang dịch..." : done ? "✓ Đã dịch" : failed ? "✗ Lỗi" : "○ Chưa dịch"}
            </span>
            <button onClick={() => translateOnePage(r.page_num)} disabled={translating}
                    className="text-xs px-2 py-1 rounded border border-indigo-200 text-indigo-600 hover:bg-indigo-50 disabled:opacity-40 disabled:cursor-not-allowed">
              {label}
            </button>
          </div>
        )
      })}
    </div>
  </div>
)}
```

- [ ] **Step 6: Typecheck**

Run (cwd `frontend`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Manual verification**

Start backend + frontend (see CLAUDE.md `/start-dev`). Open `/books/<id>` after extract: select a language, click "Dịch trang này" on one row → badge → "● Đang dịch..." → within a few seconds "✓ Đã dịch" (polling). "Dịch tất cả" uses the selected language.

- [ ] **Step 8: Commit**

```bash
git add "frontend/app/books/[id]/page.tsx"
git commit -m "feat(sp6): pipeline per-page translate + language selector + status polling"
```

---

## Task 3: Frontend Preview — "Dịch trang này" in sidebar

**Files:**
- Modify: `frontend/app/books/[id]/preview/page.tsx`
- Modify: `frontend/app/books/[id]/preview/LayoutSidebar.tsx`

Context: `preview/page.tsx` has `pages: PageInfo[]`, `currentPage`, `lang` ("en"|"vi" view toggle). `LayoutSidebar` renders the page list with status icons. We add a translate action per page that calls the V2 single-page endpoint with target lang from `localStorage.btb_translate_lang` (default "vi"), then polls `GET /pages` to refresh `has_translated`.

- [ ] **Step 1: Add translate + polling to `preview/page.tsx`**

In `frontend/app/books/[id]/preview/page.tsx`, add a ref + reload + translate handler inside the component (near the other state):
```tsx
const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

async function reloadPages() {
  try {
    const rows = await fetchAPI<PageInfo[]>(`/api/docs/${id}/pages`)
    setPages(rows)
    const anyTranslating = rows.some((r) => r.status === "translating")
    if (anyTranslating && !pollRef.current) pollRef.current = setInterval(reloadPages, 3000)
    else if (!anyTranslating && pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  } catch { /* best-effort */ }
}

async function translatePage(pageNum: number) {
  const target = localStorage.getItem("btb_translate_lang") || "vi"
  setPages((rows) => rows.map((r) => r.page_num === pageNum ? { ...r, status: "translating" } : r))
  try {
    await fetchAPI(`/api/docs/${id}/translate?async_mode=true`, {
      method: "POST",
      body: JSON.stringify({ page_num: pageNum, target_lang: target, use_v2: true }),
    })
  } catch {
    setPages((rows) => rows.map((r) => r.page_num === pageNum ? { ...r, status: "failed" } : r))
    return
  }
  if (!pollRef.current) pollRef.current = setInterval(reloadPages, 3000)
}

useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])
```
Add `useRef` to the React import: `import { useEffect, useState, useRef } from "react"`.

- [ ] **Step 2: Pass `onTranslate` to LayoutSidebar**

In `preview/page.tsx`, extend `contentProps` for the sidebar only (reader/split don't need it). Change the sidebar render to:
```tsx
{layout === "sidebar" && <LayoutSidebar {...contentProps} onTranslate={translatePage} />}
```

- [ ] **Step 3: Add the translate button in `LayoutSidebar.tsx`**

In `frontend/app/books/[id]/preview/LayoutSidebar.tsx`, extend the props type and render a small translate button per row. Change the component signature to accept an optional `onTranslate`:
```tsx
export default function LayoutSidebar({
  docId, apiUrl, pages, currentPage, lang, zoom, onPageChange,
  onTranslate,
}: ContentLayoutProps & { onTranslate?: (pageNum: number) => void }) {
```
Inside each page `<button>` row in the aside, replace the status `<span>` block with a status + translate action. Specifically, change the row to:
```tsx
<button
  key={p.page_num}
  ref={active ? activeRef : null}
  onClick={() => onPageChange(p.page_num)}
  className={`w-full text-left px-4 py-2.5 text-sm flex justify-between items-center gap-2 hover:bg-gray-50 border-b border-gray-100 ${
    active ? "bg-indigo-50 text-indigo-700 font-semibold border-l-2 border-l-indigo-500" : "text-gray-700"
  }`}
>
  <span className="flex-1">Trang {p.page_num}</span>
  <span className={`text-xs ${p.has_translated ? "text-green-600" : p.status === "translating" ? "text-blue-600" : "text-gray-400"}`}>
    {p.status === "translating" ? "●" : statusIcon(p)}
  </span>
  {onTranslate && p.status !== "translating" && (
    <span
      role="button"
      tabIndex={0}
      onClick={(e) => { e.stopPropagation(); onTranslate(p.page_num) }}
      onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); onTranslate(p.page_num) } }}
      className="text-[11px] px-1.5 py-0.5 rounded border border-indigo-200 text-indigo-600 hover:bg-indigo-100"
    >
      {p.has_translated ? "Dịch lại" : "Dịch"}
    </span>
  )}
</button>
```
(Note: use a `<span role="button">` not a nested `<button>` — nested buttons are invalid HTML.)

- [ ] **Step 4: Typecheck**

Run (cwd `frontend`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual verification**

Open `/books/<id>/preview` in Sidebar layout. Click "Dịch" on a page → icon → "●" → after a few seconds "✓"; the "Translated" toggle becomes enabled for that page and shows the Vietnamese overlay.

- [ ] **Step 6: Commit**

```bash
git add "frontend/app/books/[id]/preview/page.tsx" "frontend/app/books/[id]/preview/LayoutSidebar.tsx"
git commit -m "feat(sp6): per-page translate action in preview sidebar + status polling"
```

---

## Self-Review

**Spec coverage:**
- Dịch 1 trang + chọn ngôn ngữ → Task 1 (backend V2) + Task 2 (lang selector) + Task 3 (preview). ✅
- Trạng thái từng trang + toàn tài liệu real-time → Task 2/3 polling `GET /pages`; doc-level pipeline stepper đã tự cập nhật khi `translate_page_batch` set doc.status. ✅
- Engine V2 (Update A) → Task 1. ✅
- Pipeline + Preview (Update B) → Task 2 + Task 3. ✅
- Badge trạng thái (raw/translating/translated/failed) → Task 2 page list + Task 3 sidebar. ✅
- Polling 3s, dừng khi xong, cleanup unmount → Task 2/3. ✅
- Language localStorage `btb_translate_lang` → Task 2 (lưu) + Task 3 (đọc). ✅

**Placeholder scan:** không có TBD; mọi step có code/lệnh cụ thể. ✅

**Type consistency:** `use_v2` (model) ↔ body `{use_v2:true}` (FE); `PageRow`/`PageInfo` dùng `{page_num,status,has_original,has_translated}` khớp `GET /pages`; `translate_page_batch(...)` chữ ký khớp Task 1; `onTranslate?: (pageNum:number)=>void` khớp giữa preview/page và LayoutSidebar. ✅

**Notes:**
- `quality` mặc định "high" theo backend (spec §8) — không expose trong UI.
- Glossary/context có thể rỗng nếu chưa chạy extract-context → `translate_page_batch` degrade mượt (spec Update A).
