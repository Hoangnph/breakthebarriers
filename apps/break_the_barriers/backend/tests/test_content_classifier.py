from backend.app.services.translator_v2 import TranslatorV2


def test_is_decoration_true_for_noise():
    for s in ["206.", "LC88.01", "/0/0/", "85:1254:20", "PO52.06", "14.687.", "|", "2"]:
        assert TranslatorV2.is_decoration(s) is True, s


def test_is_decoration_false_for_content():
    for s in ["FOREWORD", "CONTENTS", "Brief history of Artificial Intelligence (AI)",
              "Algorithms : The Brains of AI", "World Travel & Tourism Council"]:
        assert TranslatorV2.is_decoration(s) is False, s


def test_translate_page_batch_drops_decoration(db_session):
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    html = ('<!DOCTYPE html><html><body>'
            '<p><span id="s1">Algorithms : The Brains of AI</span></p>'
            '<p><span id="s2">206.</span></p></body></html>')
    db_session.add(DBDocument(id="cc_doc", filename="x.pdf", total_pages=1, status="extracted"))
    db_session.add(DBPage(document_id="cc_doc", page_num=1, original_html=html, status="extracted"))
    db_session.add(DBTranslation(document_id="cc_doc", page_num=1, span_id="s1", original_text="Algorithms : The Brains of AI"))
    db_session.add(DBTranslation(document_id="cc_doc", page_num=1, span_id="s2", original_text="206."))
    db_session.commit()

    res = TranslatorV2.translate_page_batch("cc_doc", 1, "vi", {"title": "t"}, [], db_session)
    assert res["status"] == "translated"
    rows = {t.span_id: t.translated_text for t in db_session.query(DBTranslation)
            .filter(DBTranslation.document_id == "cc_doc").all()}
    assert rows["s1"]
    assert not rows["s2"]
