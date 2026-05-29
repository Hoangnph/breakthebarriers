# SP3 Web-Book Publisher — Design Spec

**Date:** 2026-05-29  
**Status:** Approved  
**Goal:** Cho phép user publish tài liệu đã dịch thành Web-Book public với URL riêng, language toggle VI/EN, và SEO metadata.

---

## 1. Scope

### Làm trong SP3
- Bảng `published_books` trong PostgreSQL
- Publish API (POST/PUT/DELETE) — owner only
- Public reader API (GET book metadata, pages, page content) — no auth nếu is_public
- Cover image: upload file tới server disk HOẶC nhập URL
- Publish modal trong dashboard (slug, title, description, cover, languages, visibility)
- Book landing page `/read/[slug]` — server-side SEO metadata
- Chapter reader `/read/[slug]/[page]` — single column, language toggle, prev/next nav
- Reader layout riêng (không có dashboard header)
- SQL migration script

### Để sau (SP5 / infra)
- Subdomain routing (`books.yourdomain.com`)
- Custom domain (Enterprise)
- Reader paywall + payment
- Sitemap.xml tự động
- Analytics (lượt đọc, conversion)

---

## 2. Architecture

```
apps/break_the_barriers/
├── backend/app/
│   ├── routers/
│   │   └── books.py              NEW — public book API + publish endpoints
│   ├── services/
│   │   └── publisher.py          NEW — slug validation, cover file handling
│   └── scripts/
│       └── migrate_sp3.sql       NEW — published_books table
│
└── frontend/app/
    ├── dashboard/page.tsx         MOD — thêm Publish button + modal
    ├── read/
    │   ├── layout.tsx             NEW — reader layout (no auth header)
    │   ├── [slug]/
    │   │   └── page.tsx           NEW — book landing page (server component, SEO)
    │   └── [slug]/
    │       └── [page]/
    │           └── page.tsx       NEW — chapter reader (client component)
    └── ...
```

**Request flow:**
```
Browser → GET /read/clean-code-vi          (Next.js SSR, no auth)
       → GET /api/books/clean-code-vi      (FastAPI, public)
       → GET /api/books/clean-code-vi/pages/1?lang=vi  (FastAPI, public)
```

---

## 3. Database

### Bảng `published_books` (mới)

```sql
CREATE TABLE published_books (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  INT     REFERENCES documents(id) ON DELETE CASCADE,
    user_id      VARCHAR REFERENCES users(id) ON DELETE SET NULL,
    slug         VARCHAR UNIQUE NOT NULL,
    title        VARCHAR NOT NULL,
    description  TEXT    DEFAULT '',
    cover_url    VARCHAR,          -- external URL (nếu nhập URL)
    cover_path   VARCHAR,          -- relative path nếu upload file
    languages    JSONB   DEFAULT '["vi"]',   -- ["vi", "en"]
    is_public    BOOLEAN DEFAULT TRUE,
    published_at TIMESTAMP DEFAULT NOW(),
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX ON published_books(slug);
CREATE INDEX ON published_books(document_id);
```

### Không thay đổi bảng hiện có
`documents`, `pages`, `translations` — chỉ đọc data từ đó.

### Static file serving
Cover uploads lưu tại `data/covers/`, served qua FastAPI static mount:
```python
app.mount("/covers", StaticFiles(directory="data/covers"), name="covers")
```

---

## 4. Backend

### 4a. Publisher service (`services/publisher.py`)

```python
import re, os, uuid
from fastapi import UploadFile

SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$')
MAX_COVER_SIZE = 5 * 1024 * 1024  # 5 MB

def validate_slug(slug: str) -> bool:
    return bool(SLUG_RE.match(slug))

def slug_from_filename(filename: str) -> str:
    """Generate slug suggestion từ tên file PDF/EPUB."""
    name = os.path.splitext(filename)[0]
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return slug[:80] if len(slug) >= 3 else slug + '-book'

async def save_cover_file(file: UploadFile, doc_id: int, slug: str) -> str:
    """Lưu cover file, trả về relative path."""
    ext = os.path.splitext(file.filename or '')[-1].lower() or '.jpg'
    filename = f"{doc_id}_{slug}{ext}"
    path = os.path.join("data", "covers", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = await file.read()
    if len(content) > MAX_COVER_SIZE:
        raise ValueError("Cover file too large (max 5MB)")
    with open(path, 'wb') as f:
        f.write(content)
    return filename
```

### 4b. Book router (`routers/books.py`)

**Publish endpoints (auth required):**

| Method | Path | Auth | Status |
|--------|------|------|--------|
| `POST` | `/api/docs/{id}/publish` | Required (owner) | 200 |
| `PUT` | `/api/books/{slug}` | Required (owner) | 200 |
| `DELETE` | `/api/books/{slug}` | Required (owner) | 200 |
| `POST` | `/api/books/{slug}/cover` | Required (owner) | 200 |

**Public endpoints (no auth nếu is_public=True):**

| Method | Path | Auth | Status |
|--------|------|------|--------|
| `GET` | `/api/books/{slug}` | Optional | 200 |
| `GET` | `/api/books/{slug}/pages` | Optional | 200 |
| `GET` | `/api/books/{slug}/pages/{page_num}` | Optional | 200 |

**Business rules:**
- Chỉ publish document có status `translated` hoặc `compiled` → 422 nếu không đủ
- Slug: lowercase, `[a-z0-9-]`, min 3, max 80 ký tự → 422 nếu invalid format
- Duplicate slug → 409 Conflict
- Private book (`is_public=False`): chỉ owner được đọc → 403 nếu không có token / sai user
- Cover file: chỉ nhận `image/*`, max 5MB → 422 nếu vi phạm
- `?lang=vi` → trả `pages.translated_html`; `?lang=en` → trả `pages.original_html`
- Nếu `translated_html` là NULL (page chưa dịch) và `?lang=vi` → fallback trả `original_html`
- Nếu ngôn ngữ yêu cầu không có trong `published_books.languages` → 400

**Multipart publish request:**
```
POST /api/docs/{id}/publish
Content-Type: multipart/form-data

slug: "clean-code-tieng-viet"
title: "Clean Code — Tiếng Việt"
description: "Cuốn sách kinh điển về viết code sạch"
languages: '["vi"]'           # JSON string
is_public: true
cover_file: <binary>          # optional, ưu tiên hơn cover_url
cover_url: ""                 # optional, dùng nếu không upload file
```

**Response:**
```json
{
  "slug": "clean-code-tieng-viet",
  "book_url": "/read/clean-code-tieng-viet",
  "title": "Clean Code — Tiếng Việt",
  "cover_url": "http://localhost:8000/covers/1_clean-code-tieng-viet.jpg"
}
```

### 4c. Pydantic models (thêm vào `models.py`)

```python
class PublishRequest(BaseModel):
    slug: str
    title: str
    description: str = ""
    languages: List[str] = ["vi"]
    is_public: bool = True
    cover_url: Optional[str] = None

class BookInfo(BaseModel):
    slug: str
    title: str
    description: str
    cover_url: Optional[str]
    languages: List[str]
    is_public: bool
    page_count: int
    published_at: datetime
    book_url: str

class BookPageInfo(BaseModel):
    page_number: int
    preview: str   # 100 ký tự đầu của original_html (stripped tags)

class BookPageContent(BaseModel):
    page_number: int
    total_pages: int
    lang: str
    html: str
    prev_page: Optional[int]
    next_page: Optional[int]
```

### 4d. Backward compatibility
- Không thay đổi bất kỳ endpoint hiện có
- 73 existing tests vẫn pass

---

## 5. Frontend

### 5a. Publish Modal (modify `dashboard/page.tsx`)

- Nút "Publish" hiện bên cạnh sách có `status ∈ {translated, compiled}`
- Click → modal overlay với form:
  - **Slug** (auto-suggest từ tên file qua `slug_from_filename`, user sửa được, validate realtime)
  - **Title** (default = tên file, có thể sửa)
  - **Description** (textarea, tùy chọn)
  - **Ngôn ngữ** — checkbox `🇻🇳 Tiếng Việt` / `🇺🇸 English`
  - **Hiển thị** — toggle Public / Private
  - **Cover** — 2 tab: "Upload file" (input file, preview thumbnail) | "Nhập URL" (text input)
  - Submit → `POST /api/docs/{id}/publish` (FormData)
  - Kết quả: hiện link `/read/{slug}` với nút Copy

### 5b. Book Landing Page `/read/[slug]` (Server Component, NEW)

```typescript
// Server component → generateMetadata() cho SEO
export async function generateMetadata({ params }) {
  const book = await fetchBookServer(params.slug)
  return {
    title: book.title,
    description: book.description,
    openGraph: {
      title: book.title,
      description: book.description,
      images: book.cover_url ? [book.cover_url] : [],
      type: "book",
    }
  }
}
```

Layout:
```
┌────────────────────────────────────────┐
│ [Cover image / gradient placeholder]   │
│ Tên sách                               │
│ 🌐 VI | EN  •  45 trang               │
│ Mô tả ngắn...                         │
│ [Bắt đầu đọc →]                       │
├────────────────────────────────────────┤
│ MỤC LỤC                               │
│  Trang 1 · Trang 2 · ... Trang 45    │
└────────────────────────────────────────┘
```

Cover placeholder: CSS gradient dùng hash của slug làm seed màu (không cần image).

### 5c. Chapter Reader `/read/[slug]/[page]` (Client Component, NEW)

```
┌────────────────────────────────────────┐
│ ← Clean Code (VI)   [VI] [EN]  2/45   │  ← sticky topbar
├────────────────────────────────────────┤
│                                        │
│   <div dangerouslySetInnerHTML>        │
│   {rendered translated HTML}           │
│                                        │
├────────────────────────────────────────┤
│ [← Trang trước]          [Trang sau→] │
└────────────────────────────────────────┘
```

- Language toggle: click VI/EN → router.push(`?lang=vi`) → re-fetch page HTML
- `dangerouslySetInnerHTML`: an toàn vì HTML từ server của mình (Docling output)
- Scroll to top khi chuyển trang

### 5d. Reader Layout (`read/layout.tsx`, NEW)

Không có auth header, không có sidebar. Chỉ có minimal topbar trong từng page.
Không thêm `/read/:path*` vào middleware matcher → public access mặc định.

### 5e. Environment
Không cần biến môi trường mới — dùng `NEXT_PUBLIC_API_URL` đã có từ SP2.

---

## 6. Testing

### Backend tests (thêm vào `test_api.py`)

```python
def test_publish_book(client, auth_headers, translated_doc):
    res = client.post(f"/api/docs/{translated_doc.id}/publish",
                      data={"slug": "test-book", "title": "Test Book",
                            "languages": '["vi"]', "is_public": "true"},
                      headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["slug"] == "test-book"

def test_publish_duplicate_slug(client, auth_headers, translated_doc):
    # publish lần 1
    client.post(f"/api/docs/{translated_doc.id}/publish",
                data={"slug": "dup-slug", "title": "T", "languages": '["vi"]'},
                headers=auth_headers)
    # publish lần 2 cùng slug → 409
    res = client.post(f"/api/docs/{translated_doc.id}/publish",
                      data={"slug": "dup-slug", "title": "T2", "languages": '["vi"]'},
                      headers=auth_headers)
    assert res.status_code == 409

def test_publish_wrong_status(client, auth_headers, raw_doc):
    res = client.post(f"/api/docs/{raw_doc.id}/publish",
                      data={"slug": "bad-doc", "title": "T", "languages": '["vi"]'},
                      headers=auth_headers)
    assert res.status_code == 422

def test_get_public_book(client, published_book):
    res = client.get(f"/api/books/{published_book.slug}")
    assert res.status_code == 200
    assert res.json()["title"] == published_book.title

def test_get_book_pages(client, published_book):
    res = client.get(f"/api/books/{published_book.slug}/pages")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_get_page_content_vi(client, published_book):
    res = client.get(f"/api/books/{published_book.slug}/pages/1?lang=vi")
    assert res.status_code == 200
    assert "html" in res.json()

def test_get_page_content_en(client, published_book):
    res = client.get(f"/api/books/{published_book.slug}/pages/1?lang=en")
    assert res.status_code == 200

def test_unpublish(client, auth_headers, published_book):
    res = client.delete(f"/api/books/{published_book.slug}", headers=auth_headers)
    assert res.status_code == 200
    res2 = client.get(f"/api/books/{published_book.slug}")
    assert res2.status_code == 404

def test_private_book_unauthorized(client, private_published_book):
    res = client.get(f"/api/books/{private_published_book.slug}")
    assert res.status_code == 403
```

### Frontend smoke tests (manual)
- [ ] Dashboard: sách status `translated` hiện nút "Publish"
- [ ] Publish modal: auto-suggest slug từ tên file, validate realtime
- [ ] Upload cover → thumbnail preview trong modal
- [ ] Sau publish: hiện link `/read/{slug}` + Copy button
- [ ] `/read/{slug}` render đúng: cover, title, description, mục lục
- [ ] `/read/{slug}/1` render HTML page 1 tiếng Việt
- [ ] Click "EN" → re-render HTML gốc tiếng Anh
- [ ] Prev/Next navigation hoạt động
- [ ] Truy cập `/read/{slug}` không cần login (public book)
- [ ] Truy cập private book không có token → 403

---

## 7. Rollout order

1. **DB migration** → tạo `published_books` + static files mount
2. **Backend** → `publisher.py` service → `books.py` router → tests
3. **Frontend** → publish modal trong dashboard → reader layout + landing page → chapter reader
4. **Integration check** → smoke tests, backward compat (73 existing tests vẫn pass)

---

## 8. Out of scope

- Subdomain routing (`books.yourdomain.com`) — cần DNS/Vercel config
- Custom domain (Enterprise) — SP5
- Paywall + reader payment (Stripe Connect) — SP5
- Sitemap.xml tự động — có thể thêm riêng sau
- Analytics (lượt đọc, revenue) — SP5
- Rate limiting trên public endpoints
- Book search / discovery page
