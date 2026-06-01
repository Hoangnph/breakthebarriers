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


def test_pydantic_glossary_models():
    from backend.app.models import GlossaryEntry, GlossaryListResponse, ExtractContextResponse
    entry = GlossaryEntry(
        id="abc", document_id="doc1", source_term="Đạo",
        target_term="Tao", target_lang="en", is_manual=False
    )
    assert entry.source_term == "Đạo"

    resp = ExtractContextResponse(
        doc_id="doc1", title="Đạo Đức Kinh", author="Lão Tử",
        domain="classical_philosophy", style="literary_poetic",
        key_terms=["Đạo", "Đức"]
    )
    assert resp.domain == "classical_philosophy"


from unittest.mock import patch, MagicMock


def test_extract_context_returns_mock_in_test():
    """In pytest environment, extract_context returns deterministic mock."""
    from backend.app.services.translator_v2 import TranslatorV2
    result = TranslatorV2.extract_document_context("test_doc", ["<p>Đạo khả đạo</p>"])
    assert "title" in result
    assert "domain" in result
    assert "style" in result
    assert isinstance(result["key_terms"], list)


def test_build_glossary_returns_list_in_test():
    """In pytest environment, build_glossary returns empty list (no key_terms)."""
    from backend.app.services.translator_v2 import TranslatorV2
    context = {"title": "Test", "domain": "general", "style": "formal_academic", "key_terms": []}
    entries = TranslatorV2.build_glossary_from_context("doc1", "vi", context)
    assert isinstance(entries, list)


def test_tm_store_and_lookup(db_session):
    """Translation memory stores and retrieves correctly."""
    from backend.app.services.translator_v2 import TranslatorV2
    TranslatorV2.tm_store("hello world", "vi", "xin chào thế giới", db_session, quality=1.0)
    hit = TranslatorV2.tm_lookup("hello world", "vi", db_session)
    assert hit == "xin chào thế giới"


def test_tm_lookup_miss(db_session):
    """TM returns None on cache miss."""
    from backend.app.services.translator_v2 import TranslatorV2
    hit = TranslatorV2.tm_lookup("nonexistent phrase xyz", "vi", db_session)
    assert hit is None
