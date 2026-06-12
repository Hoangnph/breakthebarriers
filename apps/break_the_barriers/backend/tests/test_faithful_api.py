import os
import json
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.core import DATA_DIR


def _seed(db, client, doc_id="apidoc"):
    out_dir = os.path.join(DATA_DIR, "extracted_html", doc_id)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{doc_id}-1.svg"), "w", encoding="utf-8") as f:
        f.write("<svg id='real'></svg>")
    tl = {"page_w": 400, "page_h": 300, "spans": [{"bbox": [10, 20, 80, 14], "text": "Origin"}]}
    db.add(DBDocument(id=doc_id, filename="d.pdf", total_pages=1, status="extracted"))
    db.add(DBPage(document_id=doc_id, page_num=1, status="extracted",
                  original_html='<p><span id="s1">Origin text</span></p>',
                  svg_path=f"{doc_id}-1.svg", text_layer_json=json.dumps(tl)))
    db.add(DBTranslation(document_id=doc_id, page_num=1, span_id="s1",
                         original_text="Origin text", translated_text="Bản dịch"))
    db.commit()
    return doc_id


def test_view_goc_returns_svg_with_text_layer(client, db_session):
    doc_id = _seed(db_session, client, "apidoc_goc")
    r = client.get(f"/api/docs/{doc_id}/pages/1?view=goc")
    data = r.json()
    assert "<svg id='real'></svg>" in data["html"]
    assert 'class="ff-tl"' in data["html"]
    os.remove(os.path.join(DATA_DIR, "extracted_html", doc_id, f"{doc_id}-1.svg"))


def test_view_dich_injects_translation(client, db_session):
    doc_id = _seed(db_session, client, "apidoc_dich")
    r = client.get(f"/api/docs/{doc_id}/pages/1?view=dich")
    data = r.json()
    assert "Bản dịch" in data["html"]


def test_view_goc_raw_returns_html_response(client, db_session):
    doc_id = _seed(db_session, client, "apidoc_raw")
    r = client.get(f"/api/docs/{doc_id}/pages/1?view=goc&raw=true")
    assert r.headers["content-type"].startswith("text/html")
    assert "ff-page" in r.text and "page_size" in r.text
    os.remove(os.path.join(DATA_DIR, "extracted_html", doc_id, f"{doc_id}-1.svg"))
