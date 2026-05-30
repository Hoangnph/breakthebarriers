import json
import os
import re as _re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.exc import IntegrityError
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

    if cover_url and cover_file is not None and cover_file.filename:
        raise HTTPException(status_code=422, detail="Provide either cover_url or cover_file, not both")

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
    try:
        db.commit()
        db.refresh(book)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Slug already taken")

    cu = _cover_url(book)
    return {
        "slug": book.slug,
        "book_url": _book_url(book.slug),
        "title": book.title,
        "cover_url": cu,
    }


# ---------------------------------------------------------------------------
# Public reader endpoints
# ---------------------------------------------------------------------------

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
        # vi or any non-en: prefer translated, fall back to original
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
