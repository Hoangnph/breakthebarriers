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

    r = client.post("/api/docs/cp_doc/pages/1/clean-bg?method=full")
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


def test_clean_bg_inpaint_method_sets_inpaint_file(client, db_session, monkeypatch):
    _seed_clean_photo(db_session)
    import cv2, numpy as np
    doc_dir = os.path.join(DATA_DIR, "extracted_html", "cp_doc")
    os.makedirs(doc_dir, exist_ok=True)
    cv2.imwrite(os.path.join(doc_dir, "page-1.png"), np.zeros((20, 20, 3), np.uint8))

    def _fake_inpaint(src, out, boxes, **kw):
        with open(out, "wb") as f:
            f.write(b"INP")
        return True
    monkeypatch.setattr(_image_cleaner_mod, "clean_page_background_inpaint", _fake_inpaint)

    r = client.post("/api/docs/cp_doc/pages/1/clean-bg?method=inpaint")
    assert r.status_code == 200
    assert r.json()["clean_image"] == "page-1.clean-inpaint.png"
    from backend.app.models_db import DBPage
    page = db_session.query(DBPage).filter(DBPage.document_id == "cp_doc",
                                           DBPage.page_num == 1).first()
    assert "page-1.clean-inpaint.png" in page.model_json
    for fn in ("page-1.png", "page-1.clean-inpaint.png"):
        p = os.path.join(doc_dir, fn)
        if os.path.exists(p):
            os.remove(p)


def test_set_page_policy_override(client, db_session):
    _seed_clean_photo(db_session)
    r = client.post("/api/docs/cp_doc/pages/1/policy", json={"value": "base-color"})
    assert r.status_code == 200
    assert r.json()["policy_override"] == "base-color"
    from backend.app.models_db import DBPage
    page = db_session.query(DBPage).filter(DBPage.document_id == "cp_doc",
                                           DBPage.page_num == 1).first()
    assert "base-color" in page.model_json


def test_set_page_policy_auto_clears(client, db_session):
    _seed_clean_photo(db_session)
    client.post("/api/docs/cp_doc/pages/1/policy", json={"value": "keep-raster"})
    r = client.post("/api/docs/cp_doc/pages/1/policy", json={"value": "auto"})
    assert r.status_code == 200
    assert r.json()["policy_override"] is None


def test_set_page_policy_invalid_400(client, db_session):
    _seed_clean_photo(db_session)
    r = client.post("/api/docs/cp_doc/pages/1/policy", json={"value": "nope"})
    assert r.status_code == 400


def test_clean_bg_revert_drops_clean_image(client, db_session):
    from backend.app.models_db import DBDocument, DBPage
    db_session.add(DBDocument(id="rv_doc", filename="r.pdf", total_pages=1, status="translated"))
    model = {"page_w": 595.0, "page_h": 842.0, "kind": "mixed",
             "background": {"color": "#000", "image": "page-1.png",
                            "clean_image": "page-1.clean-inpaint.png"},
             "blocks": [], "figures": [], "page_class": "regenerable", "cover": "front"}
    db_session.add(DBPage(document_id="rv_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(model)))
    db_session.commit()
    r = client.post("/api/docs/rv_doc/pages/1/clean-bg/revert")
    assert r.status_code == 200 and r.json()["status"] == "reverted"
    page = db_session.query(DBPage).filter(DBPage.document_id == "rv_doc",
                                           DBPage.page_num == 1).first()
    assert "clean-inpaint" not in page.model_json


def test_metadata_returns_override_and_has_clean(client, db_session):
    from backend.app.models_db import DBDocument, DBPage
    db_session.add(DBDocument(id="md_doc", filename="m.pdf", total_pages=1, status="translated"))
    model = {"page_w": 1.0, "page_h": 1.0, "kind": "mixed",
             "background": {"color": "#000", "image": "page-1.png",
                            "clean_image": "page-1.clean.png", "policy_override": "keep-raster"},
             "blocks": [], "figures": [], "page_class": "regenerable", "cover": "front"}
    db_session.add(DBPage(document_id="md_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(model)))
    db_session.commit()
    d = client.get("/api/docs/md_doc/pages/1").json()
    assert d["policy_override"] == "keep-raster"
    assert d["has_clean_image"] is True


def test_clean_bg_gating_respects_override(client, db_session, monkeypatch):
    from backend.app.models_db import DBDocument, DBPage
    import os, cv2, numpy as np
    db_session.add(DBDocument(id="ov_doc", filename="o.pdf", total_pages=1, status="translated"))
    model = {"page_w": 595.0, "page_h": 842.0, "kind": "mixed",
             "background": {"color": "#000", "image": "page-1.png", "policy_override": "clean-photo"},
             "blocks": [], "figures": [], "page_class": "preserve", "cover": "none"}
    db_session.add(DBPage(document_id="ov_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(model)))
    db_session.commit()
    doc_dir = os.path.join(DATA_DIR, "extracted_html", "ov_doc")
    os.makedirs(doc_dir, exist_ok=True)
    cv2.imwrite(os.path.join(doc_dir, "page-1.png"), np.zeros((10, 10, 3), np.uint8))

    def _fake_inpaint(src, out, boxes, **kw):
        open(out, "wb").write(b"X"); return True
    monkeypatch.setattr(_image_cleaner_mod, "clean_page_background_inpaint", _fake_inpaint)

    r = client.post("/api/docs/ov_doc/pages/1/clean-bg?method=inpaint")
    assert r.status_code == 200
    for fn in ("page-1.png", "page-1.clean-inpaint.png"):
        p = os.path.join(doc_dir, fn)
        if os.path.exists(p):
            os.remove(p)


def test_flow_endpoint_returns_document_html(client, db_session):
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="fl_doc", filename="f.pdf", total_pages=2, status="translated"))
    m1 = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
          "background": {"color": "#fff", "image": None},
          "blocks": [{"span_id": "h", "role": "heading", "bbox": [72, 40, 300, 28], "text": "",
                      "font": {"size": 28, "weight": 700, "italic": False, "color": "#000",
                               "align": "left", "family_class": "sans"}}],
          "figures": [], "page_class": "text", "cover": "none"}
    m2 = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
          "background": {"color": "#fff", "image": None},
          "blocks": [{"span_id": "p", "role": "body", "bbox": [72, 40, 300, 60], "text": "",
                      "font": {"size": 11, "weight": 400, "italic": False, "color": "#000",
                               "align": "left", "family_class": "sans"}}],
          "figures": [], "page_class": "text", "cover": "none"}
    db_session.add(DBPage(document_id="fl_doc", page_num=1, original_html="<p/>",
                          status="translated", model_json=json.dumps(m1)))
    db_session.add(DBPage(document_id="fl_doc", page_num=2, original_html="<p/>",
                          status="translated", model_json=json.dumps(m2)))
    db_session.add(DBTranslation(document_id="fl_doc", page_num=1, span_id="h",
                                 original_text="TITLE", translated_text="TIÊU ĐỀ"))
    db_session.add(DBTranslation(document_id="fl_doc", page_num=2, span_id="p",
                                 original_text="body", translated_text="đoạn văn dịch"))
    db_session.commit()
    r = client.get("/api/docs/fl_doc/flow?lang=vi")
    assert r.status_code == 200
    # B2.2: /flow is a faithful stack of per-page fragments (raster + translated overlay).
    assert r.text.count('class="ff-page"') == 2
    assert "page-1.png" in r.text and "page-2.png" in r.text
    assert "TIÊU ĐỀ" in r.text          # translated heading overlaid
