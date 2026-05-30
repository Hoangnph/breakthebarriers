# SP3 Web-Book Publisher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép user publish tài liệu đã dịch thành Web-Book public với URL slug riêng, language toggle VI/EN, và SEO metadata.

**Architecture:** Thêm bảng `published_books` (chỉ đọc data từ `documents`/`pages`). Backend: `publisher.py` service + `books.py` router (publish endpoints cần auth owner, public reader endpoints không cần auth). Frontend: publish modal trong dashboard + 2 page mới `/read/[slug]` (SSR, SEO) và `/read/[slug]/[page]` (reader client component) + reader layout riêng.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL (SQLite in-memory cho test), Next.js 14 App Router, Tailwind, lucide-react.

**Lưu ý quan trọng về codebase:**
- `documents.id` là **String** (vd `"clean_code"`), KHÔNG phải INT → FK `published_books.document_id` dùng String.
- `users.id` là String (uuid). FK `published_books.user_id` dùng String.
- DB models trong `backend/app/models_db.py`, pydantic models trong `backend/app/models.py`.
- Routers import: `from backend.app.database import get_db`, `from backend.app.dependencies import get_current_user, get_optional_user`.
- Tests dùng fixture `client` (SQLite in-memory, `conftest.py` pre-populate doc `clean_code` status `raw`).
- `DATA_DIR` import từ `backend.app.core`.
- Chạy test: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/ -v`
- Frontend build: `cd apps/break_the_barriers/frontend && npm run build`

---

## File Structure

| File | Trách nhiệm |
|------|-------------|
| `backend/app/models_db.py` (MOD) | Thêm class `DBPublishedBook` |
| `backend/app/models.py` (MOD) | Thêm `PublishRequest`, `BookInfo`, `BookPageInfo`, `BookPageContent` |
| `backend/app/services/publisher.py` (NEW) | `validate_slug`, `slug_from_filename`, `save_cover_file` |
| `backend/app/routers/books.py` (NEW) | Publish + public reader endpoints |
| `backend/app/main.py` (MOD) | `include_router(books.router)` + mount `/covers` static |
| `backend/scripts/migrate_sp3.sql` (NEW) | Tạo bảng `published_books` cho PostgreSQL |
| `backend/tests/test_publisher.py` (NEW) | Unit test publisher service |
| `backend/tests/test_books_api.py` (NEW) | API test publish + reader endpoints |
| `frontend/lib/api.ts` (MOD) | Thêm `API_URL` export để build cover URL |
| `frontend/app/dashboard/page.tsx` (MOD) | Thêm Publish button + modal |
| `frontend/app/read/layout.tsx` (NEW) | Reader layout (no auth header) |
| `frontend/app/read/[slug]/page.tsx` (NEW) | Book landing page (server component, SEO) |
| `frontend/app/read/[slug]/[page]/page.tsx` (NEW) | Chapter reader (client component) |

---

## Task 1: DB model `DBPublishedBook`

**Files:**
- Modify: `apps/break_the_barriers/backend/app/models_db.py`
- Test: `apps/break_the_barriers/backend/tests/test_books_api.py`

- [ ] **Step 1: Write the failing test**

Create `apps/break_the_barriers/backend/tests/test_books_api.py`:

```python
import json
import pytest
from backend.app.models_db import DBPublishedBook, DBDocument, DBPage, DBUser


def test_published_book_model_columns():
    """DBPublishedBook has the expected columns."""
    cols = DBPublishedBook.__table__.columns.keys()
    for expected in ["id", "document_id", "user_id", "slug", "title",
                     "description", "cover_url", "cover_path", "languages",
                     "is_public", "published_at", "created_at"]:
        assert expected in cols, f"missing column {expected}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py::test_published_book_model_columns -v`
Expected: FAIL with `ImportError: cannot import name 'DBPublishedBook'`

- [ ] **Step 3: Add the model**

Append to `apps/break_the_barriers/backend/app/models_db.py` (end of file):

```python
class DBPublishedBook(Base):
    __tablename__ = "published_books"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    cover_url = Column(String, nullable=True)
    cover_path = Column(String, nullable=True)
    languages = Column(Text, default='["vi"]')  # JSON-encoded list, stored as Text for SQLite compat
    is_public = Column(Boolean, default=True)
    published_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

Note: `languages` lưu dạng JSON string trong `Text` (không dùng JSONB) để tương thích SQLite test. Encode/decode bằng `json.dumps`/`json.loads` ở tầng router.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py::test_published_book_model_columns -v`
Expected: PASS

- [ ] **Step 5: Run full suite to verify no regression**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/ -q`
Expected: All existing tests still PASS (73 + 1 new)

- [ ] **Step 6: Commit**

```bash
git add apps/break_the_barriers/backend/app/models_db.py apps/break_the_barriers/backend/tests/test_books_api.py
git commit -m "feat(SP3): add DBPublishedBook model"
```

---

## Task 2: Pydantic models

**Files:**
- Modify: `apps/break_the_barriers/backend/app/models.py`
- Test: `apps/break_the_barriers/backend/tests/test_books_api.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/break_the_barriers/backend/tests/test_books_api.py`:

```python
def test_pydantic_book_models_importable():
    from backend.app.models import PublishRequest, BookInfo, BookPageInfo, BookPageContent
    req = PublishRequest(slug="my-book", title="My Book")
    assert req.languages == ["vi"]
    assert req.is_public is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py::test_pydantic_book_models_importable -v`
Expected: FAIL with `ImportError: cannot import name 'PublishRequest'`

- [ ] **Step 3: Add models**

First, add `datetime` import at top of `apps/break_the_barriers/backend/app/models.py`. Change line 2 from:

```python
from typing import List, Dict, Optional
```

to:

```python
from typing import List, Dict, Optional
from datetime import datetime
```

Then append to end of `apps/break_the_barriers/backend/app/models.py`:

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
    published_at: str
    book_url: str


class BookPageInfo(BaseModel):
    page_number: int
    preview: str


class BookPageContent(BaseModel):
    page_number: int
    total_pages: int
    lang: str
    html: str
    prev_page: Optional[int]
    next_page: Optional[int]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py::test_pydantic_book_models_importable -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/break_the_barriers/backend/app/models.py apps/break_the_barriers/backend/tests/test_books_api.py
git commit -m "feat(SP3): add publish/book pydantic models"
```

---

## Task 3: Publisher service

**Files:**
- Create: `apps/break_the_barriers/backend/app/services/publisher.py`
- Test: `apps/break_the_barriers/backend/tests/test_publisher.py`

- [ ] **Step 1: Write the failing test**

Create `apps/break_the_barriers/backend/tests/test_publisher.py`:

```python
import os
import io
import pytest
from backend.app.services.publisher import validate_slug, slug_from_filename


def test_validate_slug_accepts_valid():
    assert validate_slug("clean-code-vi") is True
    assert validate_slug("abc") is True
    assert validate_slug("book123") is True


def test_validate_slug_rejects_invalid():
    assert validate_slug("ab") is False          # too short
    assert validate_slug("UPPER") is False        # uppercase
    assert validate_slug("has space") is False    # space
    assert validate_slug("-leading") is False     # leading dash
    assert validate_slug("trailing-") is False    # trailing dash
    assert validate_slug("under_score") is False  # underscore
    assert validate_slug("a" * 81) is False       # too long


def test_slug_from_filename():
    assert slug_from_filename("Clean Code.pdf") == "clean-code"
    assert slug_from_filename("My_Book_2024.epub") == "my-book-2024"
    assert slug_from_filename("a.pdf") == "a-book"  # too short -> append suffix
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_publisher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.services.publisher'`

- [ ] **Step 3: Implement the service**

Create `apps/break_the_barriers/backend/app/services/publisher.py`:

```python
import os
import re

from fastapi import UploadFile

from backend.app.core import DATA_DIR

SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$')
MAX_COVER_SIZE = 5 * 1024 * 1024  # 5 MB
COVERS_DIR = os.path.join(DATA_DIR, "covers")


def validate_slug(slug: str) -> bool:
    """True if slug is lowercase a-z0-9-, length 3-80, no leading/trailing dash."""
    return bool(SLUG_RE.match(slug))


def slug_from_filename(filename: str) -> str:
    """Suggest a slug from a PDF/EPUB filename."""
    name = os.path.splitext(filename)[0]
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if len(slug) < 3:
        slug = (slug + '-book').strip('-')
    return slug[:80]


async def save_cover_file(file: UploadFile, doc_id: str, slug: str) -> str:
    """Save uploaded cover image to DATA_DIR/covers, return the stored filename.

    Raises ValueError if the file is too large or not an image.
    """
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise ValueError("Cover must be an image")
    content = await file.read()
    if len(content) > MAX_COVER_SIZE:
        raise ValueError("Cover file too large (max 5MB)")
    ext = os.path.splitext(file.filename or "")[-1].lower() or ".jpg"
    filename = f"{doc_id}_{slug}{ext}"
    os.makedirs(COVERS_DIR, exist_ok=True)
    with open(os.path.join(COVERS_DIR, filename), "wb") as f:
        f.write(content)
    return filename
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_publisher.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/break_the_barriers/backend/app/services/publisher.py apps/break_the_barriers/backend/tests/test_publisher.py
git commit -m "feat(SP3): add publisher service (slug validation, cover save)"
```

---

## Task 4: Publish endpoint (POST /api/docs/{id}/publish)

**Files:**
- Create: `apps/break_the_barriers/backend/app/routers/books.py`
- Modify: `apps/break_the_barriers/backend/app/main.py`
- Test: `apps/break_the_barriers/backend/tests/test_books_api.py`

This task introduces shared test fixtures used by later tasks too.

- [ ] **Step 1: Write the failing tests + fixtures**

Append to `apps/break_the_barriers/backend/tests/test_books_api.py`:

```python
from backend.app.services.auth_service import create_access_token, hash_password


@pytest.fixture
def auth_user(db_session):
    """Create a user and return (user, auth_headers)."""
    user = DBUser(email="pub@test.com", hashed_password=hash_password("secret1"), full_name="Pub")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id, user.email, user.plan)
    return user, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def translated_doc(db_session, auth_user):
    """A document owned by auth_user, status=translated, with 2 pages."""
    user, _ = auth_user
    doc = DBDocument(id="doc-trans", filename="Book.pdf", total_pages=2,
                     status="translated", user_id=user.id)
    db_session.add(doc)
    db_session.add(DBPage(document_id="doc-trans", page_num=1,
                          original_html="<p>Hello</p>", translated_html="<p>Xin chào</p>",
                          status="translated"))
    db_session.add(DBPage(document_id="doc-trans", page_num=2,
                          original_html="<p>World</p>", translated_html="<p>Thế giới</p>",
                          status="translated"))
    db_session.commit()
    return doc


def test_publish_book(client, auth_user, translated_doc):
    _, headers = auth_user
    res = client.post("/api/docs/doc-trans/publish",
                      data={"slug": "test-book", "title": "Test Book",
                            "languages": '["vi","en"]', "is_public": "true"},
                      headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["slug"] == "test-book"
    assert body["book_url"] == "/read/test-book"


def test_publish_invalid_slug(client, auth_user, translated_doc):
    _, headers = auth_user
    res = client.post("/api/docs/doc-trans/publish",
                      data={"slug": "AB", "title": "T", "languages": '["vi"]'},
                      headers=headers)
    assert res.status_code == 422


def test_publish_duplicate_slug(client, auth_user, translated_doc):
    _, headers = auth_user
    client.post("/api/docs/doc-trans/publish",
                data={"slug": "dup-slug", "title": "T", "languages": '["vi"]'},
                headers=headers)
    res = client.post("/api/docs/doc-trans/publish",
                      data={"slug": "dup-slug", "title": "T2", "languages": '["vi"]'},
                      headers=headers)
    assert res.status_code == 409


def test_publish_wrong_status(client, auth_user):
    user, headers = auth_user
    res = client.post("/api/docs/clean_code/publish",
                      data={"slug": "raw-book", "title": "T", "languages": '["vi"]'},
                      headers=headers)
    # clean_code is status=raw and not owned by this user
    assert res.status_code in (403, 422)


def test_publish_requires_auth(client, translated_doc):
    res = client.post("/api/docs/doc-trans/publish",
                      data={"slug": "noauth", "title": "T", "languages": '["vi"]'})
    assert res.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py -k publish -v`
Expected: FAIL with 404 (route not registered)

- [ ] **Step 3: Create the books router with publish endpoint**

Create `apps/break_the_barriers/backend/app/routers/books.py`:

```python
import json
import os
from typing import Optional, List

from fastapi import (APIRouter, Depends, HTTPException, Form, File, UploadFile)
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies import get_current_user, get_optional_user
from backend.app.models import BookInfo, BookPageInfo, BookPageContent
from backend.app.models_db import DBDocument, DBPage, DBPublishedBook, DBUser
from backend.app.services import publisher
from backend.app.core import DATA_DIR

router = APIRouter()

PUBLISHABLE_STATUSES = {"translated", "compiled"}


def _book_url(slug: str) -> str:
    return f"/read/{slug}"


def _cover_url(book: DBPublishedBook) -> Optional[str]:
    """Public URL for the cover: external URL takes precedence over uploaded file."""
    if book.cover_url:
        return book.cover_url
    if book.cover_path:
        return f"/covers/{book.cover_path}"
    return None


@router.post("/api/docs/{doc_id}/publish")
async def publish_book(
    doc_id: str,
    slug: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    languages: str = Form('["vi"]'),
    is_public: bool = Form(True),
    cover_url: Optional[str] = Form(None),
    cover_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(get_current_user),
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your document")
    if doc.status not in PUBLISHABLE_STATUSES:
        raise HTTPException(status_code=422, detail="Document must be translated or compiled before publishing")
    if not publisher.validate_slug(slug):
        raise HTTPException(status_code=422, detail="Invalid slug: use lowercase letters, digits, hyphens (3-80 chars)")
    if db.query(DBPublishedBook).filter(DBPublishedBook.slug == slug).first():
        raise HTTPException(status_code=409, detail="Slug already taken")

    try:
        langs = json.loads(languages)
        assert isinstance(langs, list) and langs
    except (json.JSONDecodeError, AssertionError):
        raise HTTPException(status_code=422, detail="languages must be a non-empty JSON array")

    cover_path = None
    if cover_file is not None and cover_file.filename:
        try:
            cover_path = await publisher.save_cover_file(cover_file, doc_id, slug)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    book = DBPublishedBook(
        document_id=doc_id,
        user_id=current_user.id,
        slug=slug,
        title=title,
        description=description,
        cover_url=cover_url or None,
        cover_path=cover_path,
        languages=json.dumps(langs),
        is_public=is_public,
    )
    db.add(book)
    db.commit()
    db.refresh(book)

    cu = _cover_url(book)
    return {
        "slug": book.slug,
        "book_url": _book_url(book.slug),
        "title": book.title,
        "cover_url": cu,
    }
```

- [ ] **Step 4: Register router + mount covers static in main.py**

In `apps/break_the_barriers/backend/app/main.py`, change line 7-8 from:

```python
from backend.app.routers import documents, extraction, translation, compilation, volume, jobs
from backend.app.routers import auth
```

to:

```python
from backend.app.routers import documents, extraction, translation, compilation, volume, jobs
from backend.app.routers import auth, books
```

Add after line 32 (`app.include_router(auth.router)`):

```python
app.include_router(books.router)
```

Add the static mount. After the `app.add_middleware(...)` block (after line 24), add:

```python
import os
from fastapi.staticfiles import StaticFiles
from backend.app.core import DATA_DIR

_covers_dir = os.path.join(DATA_DIR, "covers")
os.makedirs(_covers_dir, exist_ok=True)
app.mount("/covers", StaticFiles(directory=_covers_dir), name="covers")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py -k publish -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run full suite**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/ -q`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add apps/break_the_barriers/backend/app/routers/books.py apps/break_the_barriers/backend/app/main.py apps/break_the_barriers/backend/tests/test_books_api.py
git commit -m "feat(SP3): add publish endpoint + covers static mount"
```

---

## Task 5: Public reader endpoints (GET book, pages, page content)

**Files:**
- Modify: `apps/break_the_barriers/backend/app/routers/books.py`
- Test: `apps/break_the_barriers/backend/tests/test_books_api.py`

- [ ] **Step 1: Write the failing tests + fixtures**

Append to `apps/break_the_barriers/backend/tests/test_books_api.py`:

```python
import json as _json


@pytest.fixture
def published_book(client, auth_user, translated_doc):
    """Publish translated_doc and return its slug."""
    _, headers = auth_user
    client.post("/api/docs/doc-trans/publish",
                data={"slug": "pub-book", "title": "Pub Book",
                      "description": "A description",
                      "languages": '["vi","en"]', "is_public": "true"},
                headers=headers)
    return "pub-book"


@pytest.fixture
def private_book(client, auth_user, db_session):
    """Publish a private book owned by auth_user."""
    user, headers = auth_user
    doc = DBDocument(id="doc-priv", filename="Priv.pdf", total_pages=1,
                     status="translated", user_id=user.id)
    db_session.add(doc)
    db_session.add(DBPage(document_id="doc-priv", page_num=1,
                          original_html="<p>secret</p>", translated_html="<p>bí mật</p>",
                          status="translated"))
    db_session.commit()
    client.post("/api/docs/doc-priv/publish",
                data={"slug": "priv-book", "title": "Priv", "languages": '["vi"]',
                      "is_public": "false"},
                headers=headers)
    return "priv-book"


def test_get_public_book(client, published_book):
    res = client.get(f"/api/books/{published_book}")
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Pub Book"
    assert body["page_count"] == 2
    assert body["languages"] == ["vi", "en"]
    assert body["book_url"] == "/read/pub-book"


def test_get_book_404(client):
    res = client.get("/api/books/does-not-exist")
    assert res.status_code == 404


def test_get_book_pages(client, published_book):
    res = client.get(f"/api/books/{published_book}/pages")
    assert res.status_code == 200
    pages = res.json()
    assert len(pages) == 2
    assert pages[0]["page_number"] == 1
    assert "preview" in pages[0]


def test_get_page_content_vi(client, published_book):
    res = client.get(f"/api/books/{published_book}/pages/1?lang=vi")
    assert res.status_code == 200
    body = res.json()
    assert body["lang"] == "vi"
    assert "Xin chào" in body["html"]
    assert body["prev_page"] is None
    assert body["next_page"] == 2
    assert body["total_pages"] == 2


def test_get_page_content_en(client, published_book):
    res = client.get(f"/api/books/{published_book}/pages/2?lang=en")
    assert res.status_code == 200
    body = res.json()
    assert body["lang"] == "en"
    assert "World" in body["html"]
    assert body["prev_page"] == 1
    assert body["next_page"] is None


def test_get_page_lang_not_published(client, published_book):
    # Book only published with vi,en — request zh -> 400
    res = client.get(f"/api/books/{published_book}/pages/1?lang=zh")
    assert res.status_code == 400


def test_get_page_out_of_range(client, published_book):
    res = client.get(f"/api/books/{published_book}/pages/99?lang=vi")
    assert res.status_code == 404


def test_private_book_unauthorized(client, private_book):
    res = client.get(f"/api/books/{private_book}")
    assert res.status_code == 403


def test_private_book_owner_can_read(client, auth_user, private_book):
    _, headers = auth_user
    res = client.get(f"/api/books/{private_book}", headers=headers)
    assert res.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py -k "get_public_book or get_book_pages or page_content" -v`
Expected: FAIL with 404/405 (routes not registered)

- [ ] **Step 3: Implement reader endpoints**

Append to `apps/break_the_barriers/backend/app/routers/books.py`:

```python
import re as _re


def _strip_tags(html: str, limit: int = 100) -> str:
    text = _re.sub(r"<[^>]+>", " ", html or "")
    text = _re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _load_book_or_404(slug: str, db: Session) -> DBPublishedBook:
    book = db.query(DBPublishedBook).filter(DBPublishedBook.slug == slug).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


def _check_visibility(book: DBPublishedBook, user: Optional[DBUser]):
    """Private books readable only by owner."""
    if not book.is_public:
        if user is None or user.id != book.user_id:
            raise HTTPException(status_code=403, detail="This book is private")


@router.get("/api/books/{slug}", response_model=BookInfo)
def get_book(slug: str, db: Session = Depends(get_db),
             user: Optional[DBUser] = Depends(get_optional_user)):
    book = _load_book_or_404(slug, db)
    _check_visibility(book, user)
    page_count = db.query(DBPage).filter(DBPage.document_id == book.document_id).count()
    return BookInfo(
        slug=book.slug,
        title=book.title,
        description=book.description or "",
        cover_url=_cover_url(book),
        languages=json.loads(book.languages),
        is_public=book.is_public,
        page_count=page_count,
        published_at=book.published_at.isoformat(),
        book_url=_book_url(book.slug),
    )


@router.get("/api/books/{slug}/pages", response_model=List[BookPageInfo])
def get_book_pages(slug: str, db: Session = Depends(get_db),
                   user: Optional[DBUser] = Depends(get_optional_user)):
    book = _load_book_or_404(slug, db)
    _check_visibility(book, user)
    pages = (db.query(DBPage)
             .filter(DBPage.document_id == book.document_id)
             .order_by(DBPage.page_num).all())
    return [BookPageInfo(page_number=p.page_num, preview=_strip_tags(p.original_html))
            for p in pages]


@router.get("/api/books/{slug}/pages/{page_num}", response_model=BookPageContent)
def get_book_page_content(slug: str, page_num: int, lang: str = "vi",
                          db: Session = Depends(get_db),
                          user: Optional[DBUser] = Depends(get_optional_user)):
    book = _load_book_or_404(slug, db)
    _check_visibility(book, user)
    if lang not in json.loads(book.languages):
        raise HTTPException(status_code=400, detail=f"Language '{lang}' not published for this book")

    pages = (db.query(DBPage)
             .filter(DBPage.document_id == book.document_id)
             .order_by(DBPage.page_num).all())
    total = len(pages)
    page = next((p for p in pages if p.page_num == page_num), None)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")

    if lang == "en":
        html = page.original_html or ""
    else:
        # vi (or any non-en target): prefer translated, fall back to original
        html = page.translated_html or page.original_html or ""

    nums = [p.page_num for p in pages]
    idx = nums.index(page_num)
    prev_page = nums[idx - 1] if idx > 0 else None
    next_page = nums[idx + 1] if idx < total - 1 else None

    return BookPageContent(
        page_number=page_num,
        total_pages=total,
        lang=lang,
        html=html,
        prev_page=prev_page,
        next_page=next_page,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py -v`
Expected: PASS (all books tests)

- [ ] **Step 5: Run full suite**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/ -q`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add apps/break_the_barriers/backend/app/routers/books.py apps/break_the_barriers/backend/tests/test_books_api.py
git commit -m "feat(SP3): add public reader endpoints (book, pages, page content)"
```

---

## Task 6: Unpublish endpoint (DELETE /api/books/{slug})

**Files:**
- Modify: `apps/break_the_barriers/backend/app/routers/books.py`
- Test: `apps/break_the_barriers/backend/tests/test_books_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `apps/break_the_barriers/backend/tests/test_books_api.py`:

```python
def test_unpublish(client, auth_user, published_book):
    _, headers = auth_user
    res = client.delete(f"/api/books/{published_book}", headers=headers)
    assert res.status_code == 200
    res2 = client.get(f"/api/books/{published_book}")
    assert res2.status_code == 404


def test_unpublish_requires_owner(client, published_book, db_session):
    # different user
    other = DBUser(email="other@test.com", hashed_password=hash_password("secret1"))
    db_session.add(other)
    db_session.commit()
    token = create_access_token(other.id, other.email, other.plan)
    res = client.delete(f"/api/books/{published_book}",
                        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_unpublish_requires_auth(client, published_book):
    res = client.delete(f"/api/books/{published_book}")
    assert res.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py -k unpublish -v`
Expected: FAIL with 405 (DELETE not allowed)

- [ ] **Step 3: Implement DELETE endpoint**

Append to `apps/break_the_barriers/backend/app/routers/books.py`:

```python
@router.delete("/api/books/{slug}")
def unpublish_book(slug: str, db: Session = Depends(get_db),
                   current_user: DBUser = Depends(get_current_user)):
    book = _load_book_or_404(slug, db)
    if book.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your book")
    # Remove uploaded cover file if any
    if book.cover_path:
        try:
            os.remove(os.path.join(DATA_DIR, "covers", book.cover_path))
        except OSError:
            pass
    db.delete(book)
    db.commit()
    return {"ok": True, "slug": slug}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/test_books_api.py -k unpublish -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run full suite**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/ -q`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add apps/break_the_barriers/backend/app/routers/books.py apps/break_the_barriers/backend/tests/test_books_api.py
git commit -m "feat(SP3): add unpublish (DELETE) endpoint"
```

---

## Task 7: PostgreSQL migration script

**Files:**
- Create: `apps/break_the_barriers/backend/scripts/migrate_sp3.sql`

- [ ] **Step 1: Write the migration script**

Create `apps/break_the_barriers/backend/scripts/migrate_sp3.sql`:

```sql
-- SP3 Web-Book Publisher migration
-- Run against the PostgreSQL break_the_barriers database.

CREATE TABLE IF NOT EXISTS published_books (
    id           VARCHAR PRIMARY KEY,
    document_id  VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id      VARCHAR REFERENCES users(id) ON DELETE SET NULL,
    slug         VARCHAR UNIQUE NOT NULL,
    title        VARCHAR NOT NULL,
    description  TEXT    DEFAULT '',
    cover_url    VARCHAR,
    cover_path   VARCHAR,
    languages    TEXT    DEFAULT '["vi"]',
    is_public    BOOLEAN DEFAULT TRUE,
    published_at TIMESTAMP DEFAULT NOW(),
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_published_books_slug ON published_books(slug);
CREATE INDEX IF NOT EXISTS idx_published_books_document_id ON published_books(document_id);
```

Note: `id` là VARCHAR (uuid string từ Python `uuid4()`), khớp với model. `languages` là TEXT (JSON string) để model code dùng chung 1 encode/decode path với SQLite test.

- [ ] **Step 2: Verify SQL syntax (dry parse with psql if available, else skip)**

Run: `cat apps/break_the_barriers/backend/scripts/migrate_sp3.sql`
Expected: File contents print correctly. (Áp dụng vào PostgreSQL thực hiện ở bước integration; SQLite test tự tạo bảng từ model.)

- [ ] **Step 3: Commit**

```bash
git add apps/break_the_barriers/backend/scripts/migrate_sp3.sql
git commit -m "feat(SP3): add PostgreSQL migration script for published_books"
```

---

## Task 8: Frontend — Publish modal in dashboard

**Files:**
- Modify: `apps/break_the_barriers/frontend/lib/api.ts`
- Modify: `apps/break_the_barriers/frontend/app/dashboard/page.tsx`

- [ ] **Step 1: Export API_URL from lib/api.ts**

In `apps/break_the_barriers/frontend/lib/api.ts`, change line 3 from:

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
```

to:

```typescript
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
```

- [ ] **Step 2: Add PublishModal component + wire into dashboard**

In `apps/break_the_barriers/frontend/app/dashboard/page.tsx`:

Change the import on line 5 from:

```typescript
import { Upload, Trash2, Eye, LogOut } from "lucide-react"
```

to:

```typescript
import { Upload, Trash2, Eye, LogOut, Globe, X, Copy, Check } from "lucide-react"
```

Change the import on line 6 from:

```typescript
import { fetchAPI, ApiError } from "@/lib/api"
```

to:

```typescript
import { fetchAPI, ApiError, API_URL } from "@/lib/api"
```

Add the `PublishModal` component at the end of the file (after the `DashboardPage` function closes):

```typescript
function slugify(filename: string): string {
  const name = filename.replace(/\.[^.]+$/, "")
  let slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "")
  if (slug.length < 3) slug = (slug + "-book").replace(/^-+/, "")
  return slug.slice(0, 80)
}

function PublishModal({ doc, onClose }: { doc: Doc; onClose: () => void }) {
  const [slug, setSlug] = useState(slugify(doc.filename))
  const [title, setTitle] = useState(doc.filename.replace(/\.[^.]+$/, ""))
  const [description, setDescription] = useState("")
  const [langVi, setLangVi] = useState(true)
  const [langEn, setLangEn] = useState(false)
  const [isPublic, setIsPublic] = useState(true)
  const [coverTab, setCoverTab] = useState<"url" | "file">("url")
  const [coverUrl, setCoverUrl] = useState("")
  const [coverFile, setCoverFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [resultUrl, setResultUrl] = useState("")
  const [copied, setCopied] = useState(false)

  const slugValid = /^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$/.test(slug)

  async function handleSubmit() {
    setError("")
    if (!slugValid) { setError("Slug không hợp lệ (a-z, 0-9, gạch ngang, 3-80 ký tự)"); return }
    const langs: string[] = []
    if (langVi) langs.push("vi")
    if (langEn) langs.push("en")
    if (langs.length === 0) { setError("Chọn ít nhất 1 ngôn ngữ"); return }

    const form = new FormData()
    form.append("slug", slug)
    form.append("title", title)
    form.append("description", description)
    form.append("languages", JSON.stringify(langs))
    form.append("is_public", String(isPublic))
    if (coverTab === "url" && coverUrl) form.append("cover_url", coverUrl)
    if (coverTab === "file" && coverFile) form.append("cover_file", coverFile)

    setSubmitting(true)
    try {
      const res = await fetchAPI<{ book_url: string }>(
        `/api/docs/${doc.id}/publish`, { method: "POST", body: form }
      )
      setResultUrl(res.book_url)
    } catch (err) {
      if (err instanceof ApiError) setError(err.message)
      else setError("Publish thất bại")
    } finally {
      setSubmitting(false)
    }
  }

  function copyLink() {
    const full = window.location.origin + resultUrl
    navigator.clipboard.writeText(full)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
         onClick={onClose}>
      <div className="bg-white rounded-xl w-full max-w-md p-6 space-y-4"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center">
          <h3 className="font-semibold text-gray-800 flex items-center gap-2">
            <Globe size={18} className="text-indigo-600" /> Publish Web-Book
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>

        {resultUrl ? (
          <div className="space-y-3">
            <p className="text-sm text-green-700 bg-green-50 rounded-lg p-3">
              ✓ Đã publish! Link công khai:
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs bg-gray-50 border border-gray-200 rounded px-2 py-2 text-indigo-600 truncate">
                {window.location.origin + resultUrl}
              </code>
              <button onClick={copyLink}
                      className="text-gray-500 hover:text-indigo-600 p-2"
                      title="Copy">
                {copied ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
            <a href={resultUrl} target="_blank" rel="noreferrer"
               className="block text-center text-sm bg-indigo-600 text-white rounded-lg py-2 hover:bg-indigo-700">
              Mở Web-Book →
            </a>
          </div>
        ) : (
          <>
            <div>
              <label className="text-xs font-semibold text-gray-600 uppercase">URL slug</label>
              <input value={slug} onChange={(e) => setSlug(e.target.value)}
                     className={`w-full mt-1 border rounded-lg px-3 py-2 text-sm font-mono ${slugValid ? "border-gray-300" : "border-red-400"}`} />
              <p className="text-xs text-gray-400 mt-1">/read/{slug || "..."}</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 uppercase">Tiêu đề</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)}
                     className="w-full mt-1 border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 uppercase">Mô tả</label>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)}
                        rows={2}
                        className="w-full mt-1 border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div className="flex gap-4">
              <label className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={langVi} onChange={(e) => setLangVi(e.target.checked)} /> 🇻🇳 VI
              </label>
              <label className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={langEn} onChange={(e) => setLangEn(e.target.checked)} /> 🇺🇸 EN
              </label>
              <label className="flex items-center gap-1 text-sm ml-auto">
                <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} /> 🌐 Public
              </label>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 uppercase">Ảnh bìa</label>
              <div className="flex gap-2 mt-1 mb-2">
                <button onClick={() => setCoverTab("url")}
                        className={`text-xs px-3 py-1 rounded-full ${coverTab === "url" ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-500"}`}>Nhập URL</button>
                <button onClick={() => setCoverTab("file")}
                        className={`text-xs px-3 py-1 rounded-full ${coverTab === "file" ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-500"}`}>Upload file</button>
              </div>
              {coverTab === "url" ? (
                <input value={coverUrl} onChange={(e) => setCoverUrl(e.target.value)}
                       placeholder="https://..."
                       className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              ) : (
                <input type="file" accept="image/*"
                       onChange={(e) => setCoverFile(e.target.files?.[0] ?? null)}
                       className="w-full text-sm" />
              )}
            </div>

            {error && <p className="text-red-500 text-sm">{error}</p>}

            <button onClick={handleSubmit} disabled={submitting}
                    className="w-full bg-indigo-600 text-white rounded-lg py-2 text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50">
              {submitting ? "Đang publish..." : "Publish →"}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
```

Now wire it into `DashboardPage`. Add state near the other `useState` calls (after line 43, the `fileRef`):

```typescript
  const [publishDoc, setPublishDoc] = useState<Doc | null>(null)
```

Add the Publish button in the actions cell. Find the actions `<div className="flex gap-2 justify-end">` block (around line 192) and add a Publish button before the `Eye` button, but only for translated/compiled docs:

```typescript
                        {(doc.status === "translated" || doc.status === "compiled") && (
                          <button
                            onClick={() => setPublishDoc(doc)}
                            className="text-green-600 hover:text-green-800"
                            title="Publish Web-Book"
                          >
                            <Globe size={15} />
                          </button>
                        )}
```

Finally, render the modal. Just before the final closing `</div>` of the component's returned JSX (after the library card `</div>` that closes the `max-w-4xl` container), add:

```typescript
      {publishDoc && <PublishModal doc={publishDoc} onClose={() => setPublishDoc(null)} />}
```

- [ ] **Step 3: Build to verify no type/lint errors**

Run: `cd apps/break_the_barriers/frontend && npm run build`
Expected: Build succeeds (warnings OK, no errors)

- [ ] **Step 4: Commit**

```bash
git add apps/break_the_barriers/frontend/lib/api.ts apps/break_the_barriers/frontend/app/dashboard/page.tsx
git commit -m "feat(SP3): add publish modal to dashboard"
```

---

## Task 9: Frontend — Reader layout + book landing page

**Files:**
- Create: `apps/break_the_barriers/frontend/app/read/layout.tsx`
- Create: `apps/break_the_barriers/frontend/app/read/[slug]/page.tsx`

- [ ] **Step 1: Create reader layout (no auth header)**

Create `apps/break_the_barriers/frontend/app/read/layout.tsx`:

```typescript
export default function ReadLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-white text-gray-900">{children}</div>
}
```

- [ ] **Step 2: Create book landing page (server component + SEO)**

Create `apps/break_the_barriers/frontend/app/read/[slug]/page.tsx`:

```typescript
import Link from "next/link"
import { notFound } from "next/navigation"
import type { Metadata } from "next"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

interface BookInfo {
  slug: string
  title: string
  description: string
  cover_url: string | null
  languages: string[]
  is_public: boolean
  page_count: number
  published_at: string
  book_url: string
}

async function fetchBook(slug: string): Promise<BookInfo | null> {
  try {
    const res = await fetch(`${API_URL}/api/books/${slug}`, { cache: "no-store" })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

// Deterministic gradient from slug for cover placeholder
function gradientFor(slug: string): string {
  let hash = 0
  for (let i = 0; i < slug.length; i++) hash = slug.charCodeAt(i) + ((hash << 5) - hash)
  const h1 = Math.abs(hash) % 360
  const h2 = (h1 + 40) % 360
  return `linear-gradient(135deg, hsl(${h1},65%,55%), hsl(${h2},65%,45%))`
}

export async function generateMetadata(
  { params }: { params: { slug: string } }
): Promise<Metadata> {
  const book = await fetchBook(params.slug)
  if (!book) return { title: "Không tìm thấy sách" }
  return {
    title: book.title,
    description: book.description,
    openGraph: {
      title: book.title,
      description: book.description,
      images: book.cover_url ? [resolveCover(book.cover_url)] : [],
      type: "book",
    },
  }
}

function resolveCover(coverUrl: string): string {
  return coverUrl.startsWith("http") ? coverUrl : `${API_URL}${coverUrl}`
}

const LANG_LABEL: Record<string, string> = { vi: "🇻🇳 Tiếng Việt", en: "🇺🇸 English" }

export default async function BookLandingPage(
  { params }: { params: { slug: string } }
) {
  const book = await fetchBook(params.slug)
  if (!book) notFound()

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <div className="rounded-xl overflow-hidden mb-6 h-56 flex items-end p-6 text-white"
           style={book.cover_url
             ? { backgroundImage: `url(${resolveCover(book.cover_url)})`, backgroundSize: "cover", backgroundPosition: "center" }
             : { background: gradientFor(book.slug) }}>
        <h1 className="text-3xl font-bold drop-shadow">{book.title}</h1>
      </div>

      <div className="flex items-center gap-3 text-sm text-gray-500 mb-4">
        <span>{book.languages.map((l) => LANG_LABEL[l] ?? l).join(" · ")}</span>
        <span>•</span>
        <span>{book.page_count} trang</span>
      </div>

      {book.description && <p className="text-gray-700 mb-6">{book.description}</p>}

      <Link href={`/read/${book.slug}/1`}
            className="inline-block bg-indigo-600 text-white rounded-lg px-6 py-3 font-semibold hover:bg-indigo-700">
        Bắt đầu đọc →
      </Link>

      <div className="mt-10 border-t border-gray-100 pt-6">
        <h2 className="text-xs font-bold text-gray-400 uppercase mb-3">Mục lục</h2>
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: book.page_count }, (_, i) => i + 1).map((n) => (
            <Link key={n} href={`/read/${book.slug}/${n}`}
                  className="text-sm border border-gray-200 rounded-lg px-3 py-1 text-gray-600 hover:border-indigo-400 hover:text-indigo-600">
              Trang {n}
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Build to verify**

Run: `cd apps/break_the_barriers/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add apps/break_the_barriers/frontend/app/read/layout.tsx apps/break_the_barriers/frontend/app/read/[slug]/page.tsx
git commit -m "feat(SP3): add reader layout + book landing page with SEO"
```

---

## Task 10: Frontend — Chapter reader page

**Files:**
- Create: `apps/break_the_barriers/frontend/app/read/[slug]/[page]/page.tsx`

- [ ] **Step 1: Create the chapter reader (client component)**

Create `apps/break_the_barriers/frontend/app/read/[slug]/[page]/page.tsx`:

```typescript
"use client"

import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { ChevronLeft, ChevronRight, ArrowLeft } from "lucide-react"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

interface PageContent {
  page_number: number
  total_pages: number
  lang: string
  html: string
  prev_page: number | null
  next_page: number | null
}

interface BookInfo {
  title: string
  languages: string[]
}

const LANG_FLAG: Record<string, string> = { vi: "VI", en: "EN" }

export default function ChapterReaderPage(
  { params }: { params: { slug: string; page: string } }
) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const lang = searchParams.get("lang") ?? "vi"
  const pageNum = parseInt(params.page, 10)

  const [content, setContent] = useState<PageContent | null>(null)
  const [book, setBook] = useState<BookInfo | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    fetch(`${API_URL}/api/books/${params.slug}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setBook)
      .catch(() => {})
  }, [params.slug])

  useEffect(() => {
    setError("")
    setContent(null)
    fetch(`${API_URL}/api/books/${params.slug}/pages/${pageNum}?lang=${lang}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "Lỗi tải trang")
        return r.json()
      })
      .then((data: PageContent) => {
        setContent(data)
        window.scrollTo(0, 0)
      })
      .catch((e) => setError(e.message))
  }, [params.slug, pageNum, lang])

  function switchLang(newLang: string) {
    router.push(`/read/${params.slug}/${pageNum}?lang=${newLang}`)
  }

  return (
    <div>
      <header className="sticky top-0 bg-white/95 backdrop-blur border-b border-gray-200 px-4 py-3 flex items-center justify-between z-10">
        <Link href={`/read/${params.slug}`} className="flex items-center gap-1 text-sm text-gray-600 hover:text-indigo-600">
          <ArrowLeft size={16} /> {book?.title ?? "Sách"}
        </Link>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {(book?.languages ?? ["vi"]).map((l) => (
              <button key={l} onClick={() => switchLang(l)}
                      className={`text-xs px-2 py-1 rounded ${lang === l ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-500"}`}>
                {LANG_FLAG[l] ?? l.toUpperCase()}
              </button>
            ))}
          </div>
          {content && <span className="text-xs text-gray-400">{content.page_number}/{content.total_pages}</span>}
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8">
        {error && <p className="text-red-500 text-sm">{error}</p>}
        {!content && !error && <p className="text-gray-400 text-sm">Đang tải...</p>}
        {content && (
          <article className="prose max-w-none"
                   dangerouslySetInnerHTML={{ __html: content.html }} />
        )}
      </main>

      {content && (
        <nav className="max-w-2xl mx-auto px-6 pb-12 flex justify-between">
          {content.prev_page ? (
            <Link href={`/read/${params.slug}/${content.prev_page}?lang=${lang}`}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
              <ChevronLeft size={16} /> Trang trước
            </Link>
          ) : <span />}
          {content.next_page ? (
            <Link href={`/read/${params.slug}/${content.next_page}?lang=${lang}`}
                  className="flex items-center gap-1 text-sm text-indigo-600 hover:underline">
              Trang sau <ChevronRight size={16} />
            </Link>
          ) : <span />}
        </nav>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Build to verify**

Run: `cd apps/break_the_barriers/frontend && npm run build`
Expected: Build succeeds. (Nếu `useSearchParams` báo lỗi cần Suspense boundary trong static export — vì đây là client page với param động `[page]`, Next sẽ render dynamic, không lỗi. Nếu build phàn nàn, wrap nội dung trong `<Suspense>` giống pricing page.)

- [ ] **Step 3: Commit**

```bash
git add "apps/break_the_barriers/frontend/app/read/[slug]/[page]/page.tsx"
git commit -m "feat(SP3): add chapter reader page with language toggle"
```

---

## Task 11: Integration check + PostgreSQL migration apply

**Files:** none (verification only)

- [ ] **Step 1: Apply migration to local PostgreSQL**

Run:
```bash
psql postgresql://postgres:postgres@localhost:5432/break_the_barriers \
  -f apps/break_the_barriers/backend/scripts/migrate_sp3.sql
```
Expected: `CREATE TABLE` / `CREATE INDEX` output, no errors. (Nếu PostgreSQL không chạy, skip — SQLAlchemy `create_all` sẽ tạo bảng khi backend khởi động.)

- [ ] **Step 2: Run full backend test suite**

Run: `cd apps/break_the_barriers/backend && ../.venv/bin/pytest tests/ -v`
Expected: All tests PASS (73 existing + new SP3 tests, ~95 total)

- [ ] **Step 3: Frontend production build**

Run: `cd apps/break_the_barriers/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 4: Update middleware comment (confirm /read stays public)**

Verify `apps/break_the_barriers/frontend/middleware.ts` matcher does NOT include `/read`. It should remain:

```typescript
export const config = {
  matcher: ["/dashboard/:path*", "/books/:path*"],
}
```

`/read/*` is intentionally absent → public access. No change needed; this step is a confirmation.

- [ ] **Step 5: Final commit (if any doc updates)**

```bash
git add -A
git commit -m "chore(SP3): integration verification" --allow-empty
```

---

## Self-Review Notes (for the executing agent)

- **Spec coverage:** Task 1 (table) ✓; Task 2 (pydantic) ✓; Task 3 (publisher service) ✓; Tasks 4-6 (publish/reader/unpublish endpoints + 422/409/403/400/404 rules) ✓; Task 7 (migration) ✓; Task 8 (publish modal w/ cover file+URL tabs) ✓; Task 9 (landing + SEO + gradient placeholder) ✓; Task 10 (reader + lang toggle + prev/next) ✓; Task 11 (integration, /read public) ✓.
- **PUT /api/books/{slug} and POST cover endpoints** from spec section 4b are NOT in this plan — they are edit-after-publish conveniences not needed for the core publish→read flow (YAGNI). Unpublish + re-publish covers the same need for MVP. If the user wants edit-in-place later, add as a follow-up.
- **languages column** stored as JSON-encoded Text (not JSONB) for SQLite test parity — consistent across model, migration, and router.
- **Lang fallback:** `?lang=vi` with NULL translated_html falls back to original_html (spec §4b rule).
