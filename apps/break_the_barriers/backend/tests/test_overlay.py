import json
import pytest


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


def test_render_overlay_html_positions_translated_text():
    from backend.app.services.overlay_renderer import render_overlay_html
    layout = {"page_w": 1000.0, "page_h": 2000.0, "image": "page-1.png",
              "blocks": [{"span_id": "s1", "bbox": [100.0, 200.0, 300.0, 50.0], "bg": "#ffffff"}]}
    html = render_overlay_html(layout, {"s1": "Xin chào"}, "/api/docs/d1/assets")

    assert 'src="/api/docs/d1/assets/page-1.png"' in html
    assert "Xin chào" in html
    assert "left:10.000%" in html   # 100/1000
    assert "top:10.000%" in html    # 200/2000
    assert "width:30.000%" in html  # 300/1000


def test_render_overlay_empty_translations_is_raster_only():
    from backend.app.services.overlay_renderer import render_overlay_html
    layout = {"page_w": 1000.0, "page_h": 2000.0, "image": "page-1.png",
              "blocks": [{"span_id": "s1", "bbox": [100.0, 200.0, 300.0, 50.0], "bg": "#ffffff"}]}
    html = render_overlay_html(layout, {}, "/api/docs/d1/assets")
    assert 'src="/api/docs/d1/assets/page-1.png"' in html
    assert "ov-text" not in html  # không có hộp text khi không có bản dịch


def test_render_overlay_escapes_html():
    from backend.app.services.overlay_renderer import render_overlay_html
    layout = {"page_w": 100.0, "page_h": 100.0, "image": "p.png",
              "blocks": [{"span_id": "s1", "bbox": [0, 0, 100, 20], "bg": "#fff"}]}
    html = render_overlay_html(layout, {"s1": "<b>x</b>"}, "/base")
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_render_overlay_sanitizes_malicious_bg():
    from backend.app.services.overlay_renderer import render_overlay_html
    layout = {"page_w": 100.0, "page_h": 100.0, "image": "p.png",
              "blocks": [{"span_id": "s1", "bbox": [0, 0, 100, 20],
                          "bg": '"; onclick="alert(1)'}]}
    html = render_overlay_html(layout, {"s1": "hi"}, "/base")
    assert 'onclick' not in html          # malicious bg neutralized
    assert "background:#ffffff" in html   # fell back to white


def test_pages_endpoint_uses_overlay_when_layout_present(client, db_session):
    import json
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="ovapi", filename="x.pdf", total_pages=1, status="translated"))
    layout = {"page_w": 1000.0, "page_h": 2000.0, "image": "page-1.png",
              "blocks": [{"span_id": "s1", "bbox": [100.0, 200.0, 300.0, 50.0], "bg": "#ffffff"}]}
    db_session.add(DBPage(document_id="ovapi", page_num=1, original_html="<p>orig</p>",
                          status="translated", layout_json=json.dumps(layout)))
    db_session.add(DBTranslation(document_id="ovapi", page_num=1, span_id="s1",
                                 original_text="Hello", translated_text="Xin chào"))
    db_session.commit()

    vi = client.get("/api/docs/ovapi/pages/1?lang=vi").json()
    assert "Xin chào" in vi["html"]
    assert "page-1.png" in vi["html"]

    en = client.get("/api/docs/ovapi/pages/1?lang=en").json()
    assert "page-1.png" in en["html"]      # raster gốc
    assert "Xin chào" not in en["html"]     # không overlay text khi lang=en


def test_pages_endpoint_falls_back_without_layout(client, db_session):
    from backend.app.models_db import DBDocument, DBPage
    db_session.add(DBDocument(id="noov", filename="x.pdf", total_pages=1, status="extracted"))
    db_session.add(DBPage(document_id="noov", page_num=1, original_html="<p>orig-en</p>",
                          translated_html="<p>dich-vi</p>", status="translated", layout_json=None))
    db_session.commit()
    assert "orig-en" in client.get("/api/docs/noov/pages/1?lang=en").json()["html"]
    assert "dich-vi" in client.get("/api/docs/noov/pages/1?lang=vi").json()["html"]


import os

_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
       "assets", "books", "2024-wttc-introduction-to-ai.pdf"))


@pytest.mark.skipif(not os.path.exists(_PDF), reason="sample PDF not available")
def test_extract_produces_raster_and_layout(tmp_path):
    import json
    from backend.app.services.extractor import DoclingExtractor

    out = str(tmp_path / "out")
    files = DoclingExtractor.extract_pdf_to_html(_PDF, out, "wttc_it")
    assert files, "no html pages produced"

    # ít nhất 1 trang có ảnh raster + layout blocks
    layouts = [f for f in os.listdir(out) if f.endswith(".layout.json")]
    assert layouts, "no layout sidecars written"
    pngs = [f for f in os.listdir(out) if f.endswith(".png")]
    assert pngs, "no page raster images written"

    sample = json.load(open(os.path.join(out, layouts[0]), encoding="utf-8"))
    assert sample["page_w"] and sample["page_h"]
    if sample["image"]:
        assert os.path.exists(os.path.join(out, sample["image"]))


def test_items_to_page_html_bottomleft_bbox_positive_height():
    from types import SimpleNamespace
    from docling_core.types.doc import BoundingBox, CoordOrigin
    from backend.app.services.extractor import DoclingExtractor

    # BOTTOMLEFT: t (top edge) has the HIGHER y; b (bottom edge) lower y.
    bbox = BoundingBox(l=72.0, t=800.0, r=272.0, b=776.0, coord_origin=CoordOrigin.BOTTOMLEFT)
    item = SimpleNamespace(text="Hello", label="text",
                           prov=[SimpleNamespace(bbox=bbox, page_no=1)])
    page_size = SimpleNamespace(width=595.0, height=842.0)

    _html, blocks = DoclingExtractor._items_to_page_html([(item, 0)], 1, page_size)

    assert len(blocks) == 1
    l, t, w, h = blocks[0]["bbox"]
    # 842 - 800 = 42 (top), 842 - 776 = 66 (bottom) -> top=42, height=24
    assert t == 42.0
    assert h == 24.0          # positive height
    assert w == 200.0
