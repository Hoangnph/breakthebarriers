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


import os
from backend.app.core import DATA_DIR
from backend.app.services import image_cleaner as _image_cleaner_mod


def _seed_clean_photo(db_session):
    from backend.app.models_db import DBDocument, DBPage
    db_session.add(DBDocument(id="cp_doc", filename="c.pdf", total_pages=1, status="translated"))
    model = {"page_w": 595.0, "page_h": 842.0, "kind": "mixed",
             "background": {"color": "#000", "image": "page-1.png"},
             "blocks": [], "figures": [],
             "page_class": "regenerable", "cover": "front"}
    db_session.add(DBPage(document_id="cp_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(model)))
    db_session.commit()


def test_clean_bg_updates_model_json(client, db_session, monkeypatch):
    _seed_clean_photo(db_session)

    def _fake_clean(src, out, **kw):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            f.write(b"CLEAN")
        return True
    monkeypatch.setattr(_image_cleaner_mod, "clean_page_background", _fake_clean)

    r = client.post("/api/docs/cp_doc/pages/1/clean-bg")
    assert r.status_code == 200
    assert r.json()["clean_image"] == "page-1.clean.png"
    from backend.app.models_db import DBPage
    page = db_session.query(DBPage).filter(DBPage.document_id == "cp_doc",
                                           DBPage.page_num == 1).first()
    assert "page-1.clean.png" in page.model_json
    p = os.path.join(DATA_DIR, "extracted_html", "cp_doc", "page-1.clean.png")
    if os.path.exists(p):
        os.remove(p)


def test_clean_bg_rejects_non_clean_photo(client, db_session):
    _seed(db_session, _MODEL)   # _MODEL is a text page -> base-color, not clean-photo
    r = client.post("/api/docs/p_doc/pages/1/clean-bg")
    assert r.status_code == 400
