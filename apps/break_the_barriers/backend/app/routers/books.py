import json
import os
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies import get_current_user, get_optional_user
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
