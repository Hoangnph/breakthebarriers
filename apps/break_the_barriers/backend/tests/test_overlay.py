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


def test_items_to_page_html_returns_html_and_blocks():
    from types import SimpleNamespace
    from docling_core.types.doc import BoundingBox, CoordOrigin
    from backend.app.services.extractor import DoclingExtractor

    bbox = BoundingBox(l=72.0, t=40.0, r=272.0, b=64.0, coord_origin=CoordOrigin.TOPLEFT)
    item = SimpleNamespace(text="Hello world", label="text",
                           prov=[SimpleNamespace(bbox=bbox, page_no=1)])
    page_size = SimpleNamespace(width=595.0, height=842.0)

    html, blocks = DoclingExtractor._items_to_page_html([(item, 0)], 1, page_size)

    assert '<span id="s1">' in html
    assert len(blocks) == 1
    assert blocks[0]["span_id"] == "s1"
    # top-left origin: [left, top, width, height]
    assert blocks[0]["bbox"] == [72.0, 40.0, 200.0, 24.0]
