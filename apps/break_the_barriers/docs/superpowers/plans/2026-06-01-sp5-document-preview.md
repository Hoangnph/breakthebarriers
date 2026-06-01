# SP5 Document Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm trang `/books/[id]/preview` cho phép xem nội dung từng trang tài liệu với 3 layout: Reader, Sidebar, Split view.

**Architecture:** 1 client component chính (`page.tsx`) quản lý state + fetch, 3 layout component riêng biệt nhận props. Không cần backend mới — dùng `GET /api/docs/{id}/pages` và `GET /api/docs/{id}/pages/{n}?lang={en|vi}` đã có. Split view dùng `<iframe src="...&raw=true">` vì page endpoint không require auth.

**Tech Stack:** Next.js 14 App Router, React hooks, Tailwind CSS, lucide-react, `fetchAPI` từ `@/lib/api`, `getToken` từ `@/lib/auth`.

**Lưu ý codebase:**
- Token lưu trong `localStorage` key `btb_token`, lấy bằng `getToken()` từ `@/lib/auth`.
- `fetchAPI` tự thêm `Authorization: Bearer` header.
- `API_URL` export từ `@/lib/api`.
- Route `/books/[id]/preview` tự động protected bởi middleware (`/books/:path*` đã trong matcher).
- Page endpoint không cần auth → iframe `src` gọi thẳng `API_URL + /api/docs/{id}/pages/{n}?lang=en&raw=true`.
- Chạy build: `cd apps/break_the_barriers/frontend && npm run build`.

---

## File Structure

| File | Trách nhiệm |
|------|-------------|
| `frontend/app/books/[id]/preview/page.tsx` (NEW) | State, header, data fetch, layout router |
| `frontend/app/books/[id]/preview/LayoutReader.tsx` (NEW) | Layout A: full-width reader |
| `frontend/app/books/[id]/preview/LayoutSidebar.tsx` (NEW) | Layout B: sidebar + main |
| `frontend/app/books/[id]/preview/LayoutSplit.tsx` (NEW) | Layout C: split iframes |
| `frontend/app/books/[id]/page.tsx` (MOD) | Thêm nút "Xem nội dung" |

---

## Task 1: LayoutReader component

**Files:**
- Create: `apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutReader.tsx`

- [ ] **Step 1: Create LayoutReader**

Create `apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutReader.tsx`:

```typescript
import { ChevronLeft, ChevronRight } from "lucide-react"

export interface PageInfo {
  page_num: number
  status: string
  has_original: boolean
  has_translated: boolean
}

export interface ContentLayoutProps {
  pages: PageInfo[]
  currentPage: number
  html: string
  loading: boolean
  onPageChange: (page: number) => void
}

export default function LayoutReader({
  pages, currentPage, html, loading, onPageChange,
}: ContentLayoutProps) {
  const idx = pages.findIndex((p) => p.page_num === currentPage)
  const prev = idx > 0 ? pages[idx - 1].page_num : null
  const next = idx < pages.length - 1 ? pages[idx + 1].page_num : null

  return (
    <div className="flex flex-col min-h-0">
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-8">
          {loading ? (
            <div className="space-y-3 animate-pulse">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-4 bg-gray-200 rounded" style={{ width: `${70 + (i % 3) * 10}%` }} />
              ))}
            </div>
          ) : html ? (
            <article className="prose max-w-none text-sm"
                     dangerouslySetInnerHTML={{ __html: html }} />
          ) : (
            <p className="text-gray-400 text-sm text-center py-20">Không có nội dung.</p>
          )}
        </div>
      </main>

      <nav className="border-t border-gray-200 bg-white px-6 py-3 flex justify-between items-center">
        {prev !== null ? (
          <button onClick={() => onPageChange(prev)}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
            <ChevronLeft size={16} /> Trang {prev}
          </button>
        ) : <span />}
        {next !== null ? (
          <button onClick={() => onPageChange(next)}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
            Trang {next} <ChevronRight size={16} />
          </button>
        ) : <span />}
      </nav>
    </div>
  )
}
```

- [ ] **Step 2: Verify file created**

Run: `ls apps/break_the_barriers/frontend/app/books/\[id\]/preview/`
Expected: `LayoutReader.tsx`

- [ ] **Step 3: Commit**

```bash
git add "apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutReader.tsx"
git commit -m "feat(SP5): add LayoutReader component"
```

---

## Task 2: LayoutSidebar component

**Files:**
- Create: `apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutSidebar.tsx`

- [ ] **Step 1: Create LayoutSidebar**

Create `apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutSidebar.tsx`:

```typescript
import { useEffect, useRef } from "react"
import type { ContentLayoutProps } from "./LayoutReader"

export default function LayoutSidebar({
  pages, currentPage, html, loading, onPageChange,
}: ContentLayoutProps) {
  const activeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [currentPage])

  function statusIcon(p: typeof pages[0]) {
    if (p.has_translated) return "✓"
    if (p.has_original) return "○"
    return "—"
  }

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 border-r border-gray-200 bg-white overflow-y-auto">
        {pages.map((p) => {
          const active = p.page_num === currentPage
          return (
            <button
              key={p.page_num}
              ref={active ? activeRef : null}
              onClick={() => onPageChange(p.page_num)}
              className={`w-full text-left px-4 py-2.5 text-sm flex justify-between items-center hover:bg-gray-50 border-b border-gray-100 ${
                active ? "bg-indigo-50 text-indigo-700 font-semibold border-l-2 border-l-indigo-500" : "text-gray-700"
              }`}
            >
              <span>Trang {p.page_num}</span>
              <span className={`text-xs ${p.has_translated ? "text-green-600" : "text-gray-400"}`}>
                {statusIcon(p)}
              </span>
            </button>
          )
        })}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-8 py-8">
          {loading ? (
            <div className="space-y-3 animate-pulse">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-4 bg-gray-200 rounded" style={{ width: `${70 + (i % 3) * 10}%` }} />
              ))}
            </div>
          ) : html ? (
            <article className="prose max-w-none text-sm"
                     dangerouslySetInnerHTML={{ __html: html }} />
          ) : (
            <p className="text-gray-400 text-sm text-center py-20">Không có nội dung.</p>
          )}
        </div>
      </main>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add "apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutSidebar.tsx"
git commit -m "feat(SP5): add LayoutSidebar component"
```

---

## Task 3: LayoutSplit component

**Files:**
- Create: `apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutSplit.tsx`

- [ ] **Step 1: Create LayoutSplit**

Create `apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutSplit.tsx`:

```typescript
import { ChevronLeft, ChevronRight } from "lucide-react"
import type { PageInfo } from "./LayoutReader"

export interface SplitLayoutProps {
  docId: string
  pages: PageInfo[]
  currentPage: number
  apiUrl: string
  onPageChange: (page: number) => void
}

function IframePane({
  label, src, hasContent,
}: { label: string; src: string; hasContent: boolean }) {
  return (
    <div className="flex-1 flex flex-col min-w-0 border-r last:border-r-0 border-gray-200">
      <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs font-semibold text-gray-500 uppercase tracking-wide">
        {label}
      </div>
      {hasContent ? (
        <iframe
          src={src}
          className="flex-1 w-full border-none bg-white"
          title={label}
          sandbox="allow-same-origin allow-scripts"
        />
      ) : (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-400">
          Trang này chưa được dịch
        </div>
      )}
    </div>
  )
}

export default function LayoutSplit({
  docId, pages, currentPage, apiUrl, onPageChange,
}: SplitLayoutProps) {
  const idx = pages.findIndex((p) => p.page_num === currentPage)
  const currentPageInfo = pages[idx]
  const prev = idx > 0 ? pages[idx - 1].page_num : null
  const next = idx < pages.length - 1 ? pages[idx + 1].page_num : null

  const base = `${apiUrl}/api/docs/${docId}/pages/${currentPage}`
  const srcOriginal = `${base}?lang=en&raw=true`
  const srcTranslated = `${base}?lang=vi&raw=true`

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <IframePane
          label="Original"
          src={srcOriginal}
          hasContent={currentPageInfo?.has_original ?? false}
        />
        <IframePane
          label="Translated"
          src={srcTranslated}
          hasContent={currentPageInfo?.has_translated ?? false}
        />
      </div>

      <nav className="border-t border-gray-200 bg-white px-6 py-3 flex justify-between items-center">
        {prev !== null ? (
          <button onClick={() => onPageChange(prev)}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
            <ChevronLeft size={16} /> Trang {prev}
          </button>
        ) : <span />}
        {next !== null ? (
          <button onClick={() => onPageChange(next)}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
            Trang {next} <ChevronRight size={16} />
          </button>
        ) : <span />}
      </nav>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add "apps/break_the_barriers/frontend/app/books/[id]/preview/LayoutSplit.tsx"
git commit -m "feat(SP5): add LayoutSplit component"
```

---

## Task 4: Main preview page

**Files:**
- Create: `apps/break_the_barriers/frontend/app/books/[id]/preview/page.tsx`

- [ ] **Step 1: Create main preview page**

Create `apps/break_the_barriers/frontend/app/books/[id]/preview/page.tsx`:

```typescript
"use client"

import { useEffect, useState, useCallback } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, AlignJustify, LayoutTemplate, Columns2 } from "lucide-react"
import { fetchAPI, API_URL } from "@/lib/api"
import LayoutReader, { type PageInfo } from "./LayoutReader"
import LayoutSidebar from "./LayoutSidebar"
import LayoutSplit from "./LayoutSplit"

type Layout = "reader" | "sidebar" | "split"
type Lang = "en" | "vi"

interface Doc {
  id: string
  filename: string
  total_pages: number
  status: string
}

const LAYOUT_KEY = "btb_preview_layout"
const LANG_KEY = "btb_preview_lang"

const LAYOUT_ICONS = {
  reader:  { icon: AlignJustify,   label: "Reader" },
  sidebar: { icon: LayoutTemplate, label: "Sidebar" },
  split:   { icon: Columns2,       label: "Split" },
} as const

export default function PreviewPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [doc, setDoc] = useState<Doc | null>(null)
  const [pages, setPages] = useState<PageInfo[]>([])
  const [currentPage, setCurrentPage] = useState(1)
  const [layout, setLayout] = useState<Layout>("reader")
  const [lang, setLang] = useState<Lang>("en")
  const [html, setHtml] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  // Restore preferences from localStorage
  useEffect(() => {
    const savedLayout = localStorage.getItem(LAYOUT_KEY) as Layout | null
    const savedLang = localStorage.getItem(LANG_KEY) as Lang | null
    if (savedLayout && ["reader", "sidebar", "split"].includes(savedLayout)) setLayout(savedLayout)
    if (savedLang && ["en", "vi"].includes(savedLang)) setLang(savedLang)
  }, [])

  // Load document + page list on mount
  useEffect(() => {
    async function init() {
      try {
        const [docs, pageList] = await Promise.all([
          fetchAPI<Doc[]>("/api/docs"),
          fetchAPI<PageInfo[]>(`/api/docs/${id}/pages`),
        ])
        const found = docs.find((d) => d.id === id)
        if (!found) { router.push("/dashboard"); return }
        setDoc(found)
        setPages(pageList)
        if (pageList.length > 0) setCurrentPage(pageList[0].page_num)
      } catch {
        router.push("/dashboard")
      }
    }
    init()
  }, [id, router])

  // Fetch HTML when page or lang changes (not needed for split)
  const fetchHtml = useCallback(async (page: number, l: Lang) => {
    if (layout === "split") return
    setLoading(true)
    setError("")
    try {
      const data = await fetchAPI<{ html: string }>(`/api/docs/${id}/pages/${page}?lang=${l}`)
      setHtml(data.html ?? "")
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Không tải được nội dung")
      setHtml("")
    } finally {
      setLoading(false)
    }
  }, [id, layout])

  useEffect(() => {
    if (pages.length === 0) return
    fetchHtml(currentPage, lang)
    window.scrollTo(0, 0)
  }, [currentPage, lang, fetchHtml, pages.length])

  // Also re-fetch when switching away from split
  useEffect(() => {
    if (layout !== "split" && pages.length > 0) fetchHtml(currentPage, lang)
  }, [layout]) // eslint-disable-line react-hooks/exhaustive-deps

  function changeLayout(l: Layout) {
    setLayout(l)
    localStorage.setItem(LAYOUT_KEY, l)
  }

  function changeLang(l: Lang) {
    setLang(l)
    localStorage.setItem(LANG_KEY, l)
  }

  function handlePageChange(page: number) {
    setCurrentPage(page)
  }

  const currentPageInfo = pages.find((p) => p.page_num === currentPage)
  const canTranslated = currentPageInfo?.has_translated ?? false

  if (!doc) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 text-sm">Đang tải...</p>
      </div>
    )
  }

  const contentProps = { pages, currentPage, html, loading, onPageChange: handlePageChange }
  const splitProps = { docId: id, pages, currentPage, apiUrl: API_URL, onPageChange: handlePageChange }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Sticky header */}
      <header className="bg-white border-b border-gray-200 px-4 py-2.5 flex items-center gap-3 flex-shrink-0 z-10">
        {/* Back */}
        <button onClick={() => router.push(`/books/${id}`)}
                className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 flex-shrink-0">
          <ArrowLeft size={16} /> Pipeline
        </button>

        {/* Filename */}
        <span className="text-sm font-semibold text-gray-800 truncate flex-1 min-w-0">
          {doc.filename}
        </span>

        {/* Lang toggle — hidden in split */}
        {layout !== "split" && (
          <div className="flex rounded-lg border border-gray-200 overflow-hidden flex-shrink-0">
            <button onClick={() => changeLang("en")}
                    className={`px-3 py-1 text-xs font-medium ${lang === "en" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Original
            </button>
            <button onClick={() => changeLang("vi")}
                    disabled={!canTranslated}
                    className={`px-3 py-1 text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed ${lang === "vi" ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              Translated
            </button>
          </div>
        )}

        {/* Layout switcher */}
        <div className="flex rounded-lg border border-gray-200 overflow-hidden flex-shrink-0">
          {(Object.entries(LAYOUT_ICONS) as [Layout, { icon: React.ComponentType<{size?: number}>; label: string }][]).map(([key, { icon: Icon, label }]) => (
            <button key={key} onClick={() => changeLayout(key)} title={label}
                    className={`px-2.5 py-1.5 ${layout === key ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
              <Icon size={15} />
            </button>
          ))}
        </div>

        {/* Page counter */}
        <span className="text-xs text-gray-400 flex-shrink-0">
          {currentPage}/{doc.total_pages}
        </span>
      </header>

      {error && (
        <div className="bg-red-50 border-b border-red-200 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* Layout area */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {layout === "reader"  && <LayoutReader  {...contentProps} />}
        {layout === "sidebar" && <LayoutSidebar {...contentProps} />}
        {layout === "split"   && <LayoutSplit   {...splitProps} />}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build to verify**

Run: `cd apps/break_the_barriers/frontend && npm run build`

Expected: Build succeeds. Route `/books/[id]/preview` appears as `○` or `ƒ`. No type errors.

If `React.ComponentType` causes a type error in the layout switcher map, replace the type annotation with:

```typescript
{(["reader", "sidebar", "split"] as Layout[]).map((key) => {
  const { icon: Icon, label } = LAYOUT_ICONS[key]
  return (
    <button key={key} onClick={() => changeLayout(key)} title={label}
            className={`px-2.5 py-1.5 ${layout === key ? "bg-indigo-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}`}>
      <Icon size={15} />
    </button>
  )
})}
```

- [ ] **Step 3: Commit**

```bash
git add "apps/break_the_barriers/frontend/app/books/[id]/preview/page.tsx"
git commit -m "feat(SP5): add main preview page with layout router"
```

---

## Task 5: Add "Xem nội dung" button to pipeline page

**Files:**
- Modify: `apps/break_the_barriers/frontend/app/books/[id]/page.tsx`

- [ ] **Step 1: Add FileText import**

In `apps/break_the_barriers/frontend/app/books/[id]/page.tsx`, change:

```typescript
import { ArrowLeft, Play, RotateCcw, CheckCircle, Circle, Loader } from "lucide-react"
```

to:

```typescript
import { ArrowLeft, Play, RotateCcw, CheckCircle, Circle, Loader, FileText } from "lucide-react"
```

- [ ] **Step 2: Add "Xem nội dung" button**

In the actions `<div className="flex gap-3 flex-wrap">` section, add this button **after** the existing buttons (after the closing `}`  of the `translating/failed` condition block, before the closing `</div>`):

```typescript
          {doc.status !== "raw" && (
            <button
              onClick={() => router.push(`/books/${id}/preview`)}
              className="flex items-center gap-2 border border-gray-300 text-gray-600 px-4 py-2 rounded text-sm hover:bg-gray-50"
            >
              <FileText size={14} /> Xem nội dung
            </button>
          )}
```

- [ ] **Step 3: Build to verify**

Run: `cd apps/break_the_barriers/frontend && npm run build`

Expected: Build succeeds, no errors.

- [ ] **Step 4: Commit**

```bash
git add "apps/break_the_barriers/frontend/app/books/[id]/page.tsx"
git commit -m "feat(SP5): add 'Xem nội dung' button to pipeline page"
```

---

## Self-Review Notes

**Spec coverage:**
- ✅ Route `/books/[id]/preview` protected by middleware
- ✅ Header: back link, filename, lang toggle, layout switcher, page counter
- ✅ Layout A Reader: dangerouslySetInnerHTML, prev/next, scroll to top
- ✅ Layout B Sidebar: page list with status icons, active highlight, auto-scroll into view
- ✅ Layout C Split: 2 iframes with `raw=true`, "chưa dịch" fallback
- ✅ Lang toggle disabled when `has_translated = false`
- ✅ localStorage persistence for layout + lang preference
- ✅ Error handling: API errors → error banner, doc not found → redirect dashboard
- ✅ "Xem nội dung" button in pipeline page when `status !== "raw"`

**Type consistency:**
- `PageInfo` exported from `LayoutReader.tsx`, imported in `LayoutSidebar.tsx`, `LayoutSplit.tsx`, `page.tsx` — consistent across all files.
- `ContentLayoutProps` exported from `LayoutReader.tsx`, imported in `LayoutSidebar.tsx` — consistent.
- `SplitLayoutProps` defined in `LayoutSplit.tsx` — standalone.

**No placeholders:** All code blocks are complete implementations.

**YAGNI:** No re-translate button, no search within page, no zoom — view-only as spec requires.
