import json


def _seed(db_session, model):
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="p_doc", filename="x.pdf", total_pages=1, status="translated"))
    db_session.add(DBPage(document_id="p_doc", page_num=1, original_html="<p>x</p>",
                          status="translated", model_json=json.dumps(model)))
    db_session.add(DBTranslation(document_id="p_doc", page_num=1, span_id="s1",
                                 original_text="INTRODUCTION", translated_text="GIỚI THIỆU"))
    db_session.commit()


_MODEL = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
          "background": {"color": "#ffffff", "image": None},
          "blocks": [{"span_id": "s1", "role": "heading", "bbox": [72, 40, 200, 24],
                      "text": "", "font": {"size": 24, "weight": 700, "italic": False,
                                           "color": "#111", "align": "left",
                                           "family_class": "sans"}}],
          "figures": []}


def test_preview_text_page_raw_renders_text_layer_with_pagesize(client, db_session):
    _seed(db_session, _MODEL)
    r = client.get("/api/docs/p_doc/pages/1?lang=vi&raw=true")
    assert r.status_code == 200
    assert "GIỚI THIỆU" in r.text            # translated text rendered
    assert 'class="ov-bg"' not in r.text     # no raster overlay on a text page
    assert "page_size" in r.text             # raw injection preserved (preview scaling)


def test_preview_text_page_nonraw_returns_json_html(client, db_session):
    _seed(db_session, _MODEL)
    r = client.get("/api/docs/p_doc/pages/1?lang=vi")
    assert r.status_code == 200
    data = r.json()                          # non-raw must stay a JSON dict
    assert "GIỚI THIỆU" in data["html"]


def test_preview_nonraw_returns_page_class_and_cover(client, db_session):
    model = dict(_MODEL)
    model["page_class"] = "regenerable"
    model["cover"] = "front"
    _seed(db_session, model)
    r = client.get("/api/docs/p_doc/pages/1?lang=vi")
    assert r.status_code == 200
    data = r.json()
    assert data["page_class"] == "regenerable"
    assert data["cover"] == "front"
