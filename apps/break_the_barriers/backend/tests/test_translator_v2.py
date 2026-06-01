import pytest
from backend.app.models_db import DBDocumentGlossary, DBTranslationMemory, DBDocument, DBPage


def test_db_document_glossary_columns():
    cols = DBDocumentGlossary.__table__.columns.keys()
    for c in ["id", "document_id", "source_term", "target_term", "target_lang", "is_manual", "created_at"]:
        assert c in cols, f"Missing column: {c}"


def test_db_translation_memory_columns():
    cols = DBTranslationMemory.__table__.columns.keys()
    for c in ["source_hash", "source_text", "target_lang", "translated", "quality", "hit_count", "last_used"]:
        assert c in cols, f"Missing column: {c}"


def test_db_document_has_ai_metadata():
    assert "ai_metadata" in DBDocument.__table__.columns.keys()


def test_db_page_has_review_columns():
    cols = DBPage.__table__.columns.keys()
    assert "needs_review" in cols
    assert "review_reason" in cols
    assert "translation_quality" in cols
