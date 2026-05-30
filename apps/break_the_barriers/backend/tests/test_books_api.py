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
