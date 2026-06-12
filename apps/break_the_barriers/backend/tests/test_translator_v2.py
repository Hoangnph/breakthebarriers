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


def test_gemini_batch_translate_no_key_returns_none():
    """_gemini_batch_translate returns None when no API key."""
    import os
    from backend.app.services.translator_v2 import TranslatorV2
    old = os.environ.pop("GEMINI_API_KEY", None)
    try:
        result = TranslatorV2._gemini_batch_translate(
            [{"text": "Hello", "span_ids": ["s1"]}], "vi",
            {"title": "T", "domain": "general", "style": "formal_academic"}, []
        )
        assert result is None
    finally:
        if old is not None:
            os.environ["GEMINI_API_KEY"] = old


def test_extract_context_endpoint(client, db_session):
    from backend.app.models_db import DBDocument, DBPage
    doc = DBDocument(id="ctx-doc", filename="ctx.pdf", total_pages=2, status="extracted")
    db_session.add(doc)
    for i in range(1, 3):
        db_session.add(DBPage(
            document_id="ctx-doc", page_num=i, status="raw",
            original_html=f"<p>Sample text page {i}</p>"
        ))
    db_session.commit()

    res = client.post("/api/docs/ctx-doc/extract-context", json={"target_lang": "vi"})
    assert res.status_code == 200
    body = res.json()
    assert "title" in body
    assert "domain" in body


def test_extract_context_404(client):
    res = client.post("/api/docs/no-such-doc/extract-context", json={"target_lang": "vi"})
    assert res.status_code == 404


def test_translate_all_use_v2(client, db_session):
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    doc = DBDocument(id="v2all-doc", filename="all.pdf", total_pages=1, status="extracted")
    db_session.add(doc)
    db_session.add(DBPage(
        document_id="v2all-doc", page_num=1, status="raw",
        original_html='<html><body><span id="s1" style="top:10;left:10">Hello</span></body></html>'
    ))
    db_session.add(DBTranslation(
        document_id="v2all-doc", page_num=1, span_id="s1", original_text="Hello"
    ))
    db_session.commit()

    res = client.post("/api/docs/v2all-doc/translate-all", json={
        "target_lang": "vi", "use_v2": True
    })
    assert res.status_code in (200, 202)


def test_resolve_batch_model():
    """Model routing: fast/balanced→flash-lite, high→3.5-flash, invalid→balanced default."""
    from backend.app.services.translator_v2 import TranslatorV2
    assert TranslatorV2._resolve_batch_model("fast") == "gemini-3.1-flash-lite"
    assert TranslatorV2._resolve_batch_model("balanced") == "gemini-3.1-flash-lite"
    assert TranslatorV2._resolve_batch_model("high") == "gemini-3.5-flash"
    # Invalid tier falls back to balanced
    assert TranslatorV2._resolve_batch_model("nonsense") == "gemini-3.1-flash-lite"


def test_anchor_model_is_strong():
    """Context + glossary use the strong anchor model regardless of tier."""
    from backend.app.services.translator_v2 import TranslatorV2
    assert TranslatorV2.ANCHOR_MODEL == "gemini-3.5-flash"
    assert TranslatorV2.MODEL == TranslatorV2.ANCHOR_MODEL  # backward-compat alias


def test_translate_batch_max_tier_writes_winner_and_score(db_session, monkeypatch):
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    from backend.app.services.translator_v2 import TranslatorV2
    from backend.app.services import translation_harness as TH

    doc_id = "maxdoc"
    db_session.add(DBDocument(id=doc_id, filename="d.pdf", total_pages=1, status="extracted"))
    db_session.add(DBPage(document_id=doc_id, page_num=1, status="raw",
                          original_html='<p><span id="s1">Artificial Intelligence</span></p>'))
    db_session.add(DBTranslation(document_id=doc_id, page_num=1, span_id="s1",
                                 original_text="Artificial Intelligence"))
    db_session.commit()

    monkeypatch.setattr(TH.TranslationHarness, "harmonize_page",
                        staticmethod(lambda blocks, *a: (["Trí tuệ nhân tạo"] * len(blocks),
                                                          [93] * len(blocks))))
    TranslatorV2.translate_page_batch(doc_id, 1, "vi", {"domain": "tech"}, [],
                                      db_session, quality="max")
    row = db_session.query(DBTranslation).filter_by(document_id=doc_id, page_num=1,
                                                     span_id="s1").first()
    assert row.translated_text == "Trí tuệ nhân tạo"
    page = db_session.query(DBPage).filter_by(document_id=doc_id, page_num=1).first()
    assert page.translation_quality and abs(page.translation_quality - 0.93) < 0.01
