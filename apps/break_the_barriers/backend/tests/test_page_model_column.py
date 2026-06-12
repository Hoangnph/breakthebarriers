import json


def test_dbpage_has_model_json_column(db_session):
    from backend.app.models_db import DBPage, DBDocument
    db_session.add(DBDocument(id="m_doc", filename="x.pdf", total_pages=1, status="extracted"))
    db_session.commit()
    payload = json.dumps({"page_w": 595.0, "page_h": 842.0, "kind": "text",
                          "background": {"color": "#fff", "image": None},
                          "blocks": [], "figures": []})
    db_session.add(DBPage(document_id="m_doc", page_num=1, original_html="<p>x</p>",
                          status="extracted", model_json=payload))
    db_session.commit()
    page = db_session.query(DBPage).filter(DBPage.document_id == "m_doc").first()
    assert json.loads(page.model_json)["kind"] == "text"
