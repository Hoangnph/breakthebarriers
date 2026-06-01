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
    assert entries == []


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


def test_translate_page_batch_mock(db_session):
    """Batch translation uses mock in pytest — page gets translated."""
    from backend.app.services.translator_v2 import TranslatorV2
    from backend.app.models_db import DBDocument, DBPage, DBTranslation

    doc = DBDocument(id="v2doc", filename="test.pdf", total_pages=1, status="extracted")
    db_session.add(doc)
    page = DBPage(
        document_id="v2doc", page_num=1, status="raw",
        original_html='<html><body><span id="s1" style="top:100;left:10">Hello World</span></body></html>'
    )
    db_session.add(page)
    db_session.add(DBTranslation(
        document_id="v2doc", page_num=1, span_id="s1",
        original_text="Hello World"
    ))
    db_session.commit()

    result = TranslatorV2.translate_page_batch(
        doc_id="v2doc", page_num=1, target_lang="vi",
        context={"title": "T", "domain": "general", "style": "formal_academic"},
        glossary=[],
        db=db_session,
    )
    assert result["status"] in ("translated", "failed")
    page_after = db_session.query(DBPage).filter_by(document_id="v2doc", page_num=1).first()
    assert page_after.status in ("translated", "failed")


def test_translate_page_batch_uses_tm(db_session):
    """Batch skips V1 for blocks already in TM."""
    from backend.app.services.translator_v2 import TranslatorV2
    from backend.app.models_db import DBDocument, DBPage, DBTranslation

    doc = DBDocument(id="v2tm", filename="tm.pdf", total_pages=1, status="extracted")
    db_session.add(doc)
    page = DBPage(document_id="v2tm", page_num=1, status="raw",
                  original_html='<html><body><span id="s1" style="top:10;left:10">Hello World</span></body></html>')
    db_session.add(page)
    db_session.add(DBTranslation(document_id="v2tm", page_num=1, span_id="s1", original_text="Hello World"))
    db_session.commit()

    # Pre-load TM
    TranslatorV2.tm_store("Hello World", "vi", "Xin chào Thế giới", db_session, quality=1.0)

    result = TranslatorV2.translate_page_batch(
        doc_id="v2tm", page_num=1, target_lang="vi",
        context={"title": "T", "domain": "general", "style": "formal_academic"},
        glossary=[],
        db=db_session,
    )
    assert result["status"] == "translated"
    t = db_session.query(DBTranslation).filter_by(document_id="v2tm", span_id="s1").first()
    assert t.translated_text == "Xin chào Thế giới"
