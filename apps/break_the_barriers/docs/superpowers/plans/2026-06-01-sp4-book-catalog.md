# SP4 Public Book Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm trang `/library` công khai hiển thị tất cả web-book đã publish, với tìm kiếm theo tiêu đề và lọc theo ngôn ngữ.

**Architecture:** Backend thêm `GET /api/books` (list public books, filter `q`/`lang`, pagination) vào `routers/books.py`. Frontend tạo `/library` (Next.js Server Component, SSR) render grid card từ searchParams. Không có route mới trong middleware matcher — `/library` public mặc định.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, SQLite in-memory (test), Next.js 14 App Router, Tailwind, lucide-react.

**Lưu ý codebase:**
- `documents.id` là String; `DBPublishedBook.languages` là JSON Text (`json.loads`/`json.dumps`).
- `BookInfo` model đã có trong `backend/app/models.py` — reuse hoàn toàn.
- Helper `_cover_url(book)` và `_book_url(slug)` đã có trong `routers/books.py`.
- Chạy test: `cd apps/break_the_barriers/backend && .venv/bin/pytest tests/ -v` (venv ở `apps/break_the_barriers/backend/.venv/`).
- Frontend build: `cd apps/break_the_barriers/frontend && npm run build`.
- API_URL pattern: `const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"`.

---

## File Structure

| File | Trách nhiệm |
|------|-------------|
| `backend/app/models.py` (MOD) | Thêm `BookListResponse` |
| `backend/app/routers/books.py` (MOD) | Thêm `GET /api/books` endpoint |
| `backend/tests/test_books_api.py` (MOD) | Thêm tests cho list endpoint |
| `frontend/app/library/page.tsx` (NEW) | Catalog page (Server Component) |

---

## Task 1: Backend — `GET /api/books` endpoint

**Files:**
- Modify: `apps/break_the_barriers/backend/app/models.py`
- Modify: `apps/break_the_barriers/backend/app/routers/books.py`
- Test: `apps/break_the_barriers/backend/tests/test_books_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `apps/break_the_barriers/backend/tests/test_books_api.py`:

```python
def test_list_books_returns_public(client, published_book):
    res = client.get("/api/books")
    assert res.status_code == 200
    body = res.json()
    assert "books" in body and "total" in body
    assert body["total"] >= 1
    slugs = [b["slug"] for b in body["books"]]
    assert published_book in slugs


def test_list_books_excludes_private(client, published_book, private_book):
    res = client.get("/api/books")
    assert res.status_code == 200
    slugs = [b["slug"] for b in res.json()["books"]]
    assert private_book not in slugs


def test_list_books_search_match(client, published_book):
    res = client.get("/api/books?q=Pub")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert any(b["slug"] == published_book for b in body["books"])


def test_list_books_search_no_match(client, published_book):
    res = client.get("/api/books?q=zzznomatch")
    assert res.status_code == 200
    assert res.json()["total"] == 0
    assert res.json()["books"] == []


def test_list_books_lang_filter(client, published_book):
    # published_book has languages=["vi","en"]
    res = client.get("/api/books?lang=vi")
    assert res.status_code == 200
    assert any(b["slug"] == published_book for b in res.json()["books"])


def test_list_books_lang_filter_excludes(client, published_book):
    # No book with lang=zh should be in results
    res = client.get("/api/books?lang=zh")
    assert res.status_code == 200
    slugs = [b["slug"] for b in res.json()["books"]]
    assert published_book not in slugs


def test_list_books_pagination(client, published_book):
    res = client.get("/api/books?per_page=1&page=1")
    assert res.status_code == 200
    body = res.json()
    assert len(body["books"]) <= 1
    assert body["per_page"] == 1
    assert body["page"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/break_the_barriers/backend && .venv/bin/pytest tests/test_books_api.py -k "list_books" -v`

Expected: FAIL with `404` (route not registered yet)

- [ ] **Step 3: Add `BookListResponse` pydantic model**

Append to end of `apps/break_the_barriers/backend/app/models.py`:

```python
class BookListResponse(BaseModel):
    books: List[BookInfo]
    total: int
    page: int
    per_page: int
```

- [ ] **Step 4: Add `GET /api/books` endpoint to books router**

In `apps/break_the_barriers/backend/app/routers/books.py`, add this import at the top of the file (after existing imports):

```python
from sqlalchemy import func
```

Then append the new endpoint **before** the `@router.get("/api/books/{slug}")` line (insert before line 128 — the slug endpoint must come AFTER the list endpoint to avoid FastAPI treating `""` as a slug):

```python
@router.get("/api/books", response_model=BookListResponse)
def list_books(
    q: Optional[str] = None,
    lang: Optional[str] = None,
    page: int = 1,
    per_page: int = 12,
    db: Session = Depends(get_db),
):
    query = db.query(DBPublishedBook).filter(DBPublishedBook.is_public == True)  # noqa: E712
    if q:
        query = query.filter(DBPublishedBook.title.ilike(f"%{q}%"))
    if lang:
        # languages is a JSON text like '["vi","en"]' — use LIKE for simple containment
        query = query.filter(DBPublishedBook.languages.contains(f'"{lang}"'))
    total = query.count()
    books_db = (query
                .order_by(DBPublishedBook.published_at.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all())

    result = []
    for book in books_db:
        page_count = db.query(func.count(DBPage.id)).filter(
            DBPage.document_id == book.document_id
        ).scalar() or 0
        result.append(BookInfo(
            slug=book.slug,
            title=book.title,
            description=book.description or "",
            cover_url=_cover_url(book),
            languages=json.loads(book.languages),
            is_public=book.is_public,
            page_count=page_count,
            published_at=book.published_at.isoformat(),
            book_url=_book_url(book.slug),
        ))
    return BookListResponse(books=result, total=total, page=page, per_page=per_page)
```

Also add `BookListResponse` to the models import line. Change:

```python
from backend.app.models import BookInfo, BookPageInfo, BookPageContent
```

to:

```python
from backend.app.models import BookInfo, BookListResponse, BookPageInfo, BookPageContent
```

**IMPORTANT — route order:** The `GET /api/books` endpoint MUST be registered BEFORE `GET /api/books/{slug}`. In FastAPI, literal routes take precedence when ordered first. Verify the `@router.get("/api/books", ...)` decorator appears before `@router.get("/api/books/{slug}", ...)` in the file.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/break_the_barriers/backend && .venv/bin/pytest tests/test_books_api.py -k "list_books" -v`

Expected: 7 PASS

- [ ] **Step 6: Run full suite**

Run: `cd apps/break_the_barriers/backend && .venv/bin/pytest tests/ -q`

Expected: All PASS (107 total)

- [ ] **Step 7: Commit**

```bash
git add apps/break_the_barriers/backend/app/models.py \
        apps/break_the_barriers/backend/app/routers/books.py \
        apps/break_the_barriers/backend/tests/test_books_api.py
git commit -m "feat(SP4): add GET /api/books list endpoint with search and lang filter"
```

---

## Task 2: Frontend — `/library` catalog page

**Files:**
- Create: `apps/break_the_barriers/frontend/app/library/page.tsx`

- [ ] **Step 1: Create the catalog page**

Create `apps/break_the_barriers/frontend/app/library/page.tsx`:

```typescript
import Link from "next/link"
import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Thư viện sách | Break The Barriers",
  description: "Khám phá các web-book song ngữ được xuất bản bởi cộng đồng.",
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

interface BookInfo {
  slug: string
  title: string
  description: string
  cover_url: string | null
  languages: string[]
  page_count: number
  published_at: string
  book_url: string
}

interface BookListResponse {
  books: BookInfo[]
  total: number
  page: number
  per_page: number
}

async function fetchBooks(q: string, lang: string, page: number): Promise<BookListResponse> {
  const params = new URLSearchParams()
  if (q) params.set("q", q)
  if (lang) params.set("lang", lang)
  params.set("page", String(page))
  params.set("per_page", "12")
  try {
    const res = await fetch(`${API_URL}/api/books?${params}`, { cache: "no-store" })
    if (!res.ok) return { books: [], total: 0, page: 1, per_page: 12 }
    return res.json()
  } catch {
    return { books: [], total: 0, page: 1, per_page: 12 }
  }
}

// Deterministic gradient from slug (same logic as /read/[slug])
function gradientFor(slug: string): string {
  let hash = 0
  for (let i = 0; i < slug.length; i++) hash = slug.charCodeAt(i) + ((hash << 5) - hash)
  const h1 = Math.abs(hash) % 360
  const h2 = (h1 + 40) % 360
  return `linear-gradient(135deg, hsl(${h1},65%,55%), hsl(${h2},65%,45%))`
}

function resolveCover(coverUrl: string): string {
  return coverUrl.startsWith("http") ? coverUrl : `${API_URL}${coverUrl}`
}

const LANG_LABEL: Record<string, string> = { vi: "🇻🇳 VI", en: "🇺🇸 EN" }

const LANG_OPTIONS = [
  { value: "", label: "Tất cả" },
  { value: "vi", label: "🇻🇳 Tiếng Việt" },
  { value: "en", label: "🇺🇸 English" },
]

export default async function LibraryPage({
  searchParams,
}: {
  searchParams: { q?: string; lang?: string; page?: string }
}) {
  const q = searchParams.q ?? ""
  const lang = searchParams.lang ?? ""
  const page = Math.max(1, parseInt(searchParams.page ?? "1", 10) || 1)

  const data = await fetchBooks(q, lang, page)
  const totalPages = Math.ceil(data.total / data.per_page)

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-8">
        <div className="max-w-5xl mx-auto">
          <h1 className="text-3xl font-bold text-gray-900 mb-1">Thư viện sách</h1>
          <p className="text-gray-500 text-sm mb-6">
            {data.total} web-book song ngữ được cộng đồng xuất bản
          </p>

          {/* Search + filter form */}
          <form className="flex flex-col sm:flex-row gap-3">
            <input
              name="q"
              defaultValue={q}
              placeholder="Tìm kiếm theo tiêu đề..."
              className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <select
              name="lang"
              defaultValue={lang}
              className="border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              {LANG_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <button
              type="submit"
              className="bg-indigo-600 text-white rounded-lg px-5 py-2 text-sm font-semibold hover:bg-indigo-700"
            >
              Tìm
            </button>
          </form>
        </div>
      </div>

      {/* Book grid */}
      <div className="max-w-5xl mx-auto px-6 py-8">
        {data.books.length === 0 ? (
          <p className="text-center text-gray-400 py-20 text-sm">
            {q || lang ? "Không tìm thấy sách phù hợp." : "Chưa có sách nào được xuất bản."}
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
            {data.books.map((book) => (
              <Link key={book.slug} href={`/read/${book.slug}`} className="group block">
                <div className="bg-white rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow border border-gray-100">
                  {/* Cover */}
                  <div
                    className="h-36 flex items-end p-3"
                    style={
                      book.cover_url
                        ? {
                            backgroundImage: `url(${resolveCover(book.cover_url)})`,
                            backgroundSize: "cover",
                            backgroundPosition: "center",
                          }
                        : { background: gradientFor(book.slug) }
                    }
                  >
                    <div className="flex gap-1 flex-wrap">
                      {book.languages.map((l) => (
                        <span
                          key={l}
                          className="text-xs bg-black/30 text-white rounded px-2 py-0.5 backdrop-blur-sm"
                        >
                          {LANG_LABEL[l] ?? l.toUpperCase()}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Info */}
                  <div className="p-4">
                    <h2 className="font-semibold text-gray-800 text-sm leading-snug group-hover:text-indigo-600 line-clamp-2 mb-1">
                      {book.title}
                    </h2>
                    {book.description && (
                      <p className="text-xs text-gray-500 line-clamp-2 mb-2">{book.description}</p>
                    )}
                    <span className="text-xs text-gray-400">{book.page_count} trang</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-center gap-3 mt-10">
            {page > 1 && (
              <Link
                href={`/library?q=${q}&lang=${lang}&page=${page - 1}`}
                className="text-sm text-indigo-600 hover:underline"
              >
                ← Trang trước
              </Link>
            )}
            <span className="text-sm text-gray-400">
              {page} / {totalPages}
            </span>
            {page < totalPages && (
              <Link
                href={`/library?q=${q}&lang=${lang}&page=${page + 1}`}
                className="text-sm text-indigo-600 hover:underline"
              >
                Trang sau →
              </Link>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build to verify**

Run: `cd apps/break_the_barriers/frontend && npm run build`

Expected: Build succeeds. Route `/library` appears as `○` (static) or `ƒ` (dynamic) — both are fine. No errors.

If build fails with `searchParams` type error in Next.js 14.2+, the `searchParams` prop type may need to be `Promise<{...}>`. In that case, change the component signature to:

```typescript
export default async function LibraryPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; lang?: string; page?: string }>
}) {
  const { q: rawQ, lang: rawLang, page: rawPage } = await searchParams
  const q = rawQ ?? ""
  const lang = rawLang ?? ""
  const page = Math.max(1, parseInt(rawPage ?? "1", 10) || 1)
  // rest of the function unchanged
```

- [ ] **Step 3: Commit**

```bash
git add "apps/break_the_barriers/frontend/app/library/page.tsx"
git commit -m "feat(SP4): add /library public book catalog page"
```

---

## Self-Review Notes

- **Spec coverage:** `GET /api/books` with `q`/`lang`/`page`/`per_page` ✓; private books excluded ✓; `/library` page with grid + search form + lang filter + pagination ✓; `/library` public (not in middleware matcher) ✓.
- **Route order:** `GET /api/books` inserted BEFORE `GET /api/books/{slug}` to prevent FastAPI slug collision — documented in Task 1 Step 4.
- **Lang filter:** JSON-text LIKE containment (`'"vi"'`) handles `["vi","en"]` correctly without JSONB — consistent with SP3 pattern.
- **YAGNI:** No tag system, no author pages, no sorting UI — catalog MVP only.
- **`line-clamp-2`:** Tailwind CSS v3+ includes this utility natively — no plugin needed.
