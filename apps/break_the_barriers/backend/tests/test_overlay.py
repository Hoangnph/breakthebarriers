import json


def test_dbpage_has_layout_json_column(db_session):
    from backend.app.models_db import DBPage, DBDocument
    db_session.add(DBDocument(id="ov_doc", filename="x.pdf", total_pages=1, status="extracted"))
    db_session.commit()
    payload = json.dumps({"page_w": 595.0, "page_h": 842.0, "image": "page-1.png", "blocks": []})
    db_session.add(DBPage(document_id="ov_doc", page_num=1, original_html="<p>x</p>",
                          status="extracted", layout_json=payload))
    db_session.commit()
    page = db_session.query(DBPage).filter(DBPage.document_id == "ov_doc").first()
    assert json.loads(page.layout_json)["image"] == "page-1.png"


def test_save_and_sample_bg_color(tmp_path):
    from PIL import Image
    from backend.app.services.page_image import save_page_image, sample_bg_color

    img = Image.new("RGB", (100, 50), (10, 20, 30))  # màu biết trước
    fname = save_page_image(img, str(tmp_path), "doc1", 7)
    assert fname == "page-7.png"
    assert (tmp_path / "page-7.png").exists()

    color = sample_bg_color(str(tmp_path / "page-7.png"), (0, 0, 100, 50))
    assert color == "#0a141e"  # (10,20,30) hex


def test_sample_bg_color_missing_file_defaults_white():
    from backend.app.services.page_image import sample_bg_color
    assert sample_bg_color("/nonexistent/x.png", (0, 0, 10, 10)) == "#ffffff"
