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


def test_pydantic_book_models_importable():
    from backend.app.models import PublishRequest, BookInfo, BookPageInfo, BookPageContent
    req = PublishRequest(slug="my-book", title="My Book")
    assert req.languages == ["vi"]
    assert req.is_public is True
