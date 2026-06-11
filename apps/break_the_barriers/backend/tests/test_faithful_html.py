import os
import fitz
from backend.app.services.text_layer import build_blocks, build_drawings
from backend.app.services.faithful_html_renderer import render_blocks_page


def _pdf_with_shapes(path):
    """1-page PDF: heading + body text + 1 line + 1 filled rect (vector)."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((20, 40), "Heading Big", fontsize=20)
    page.insert_text((20, 70), "body text line", fontsize=10)
    page.draw_line(fitz.Point(20, 90), fitz.Point(280, 90), color=(0, 0, 1), width=1)
    page.draw_rect(fitz.Rect(20, 100, 120, 150), color=(1, 0, 0), fill=(0.9, 0.9, 0.9))
    doc.save(path)
    doc.close()


def test_build_blocks_structure(tmp_path):
    p = str(tmp_path / "s.pdf"); _pdf_with_shapes(p)
    doc = fitz.open(p); el = build_blocks(doc[0]); doc.close()
    assert el["page_w"] == 300 and el["page_h"] == 200
    assert el["blocks"], "should group text into blocks"
    sp = el["blocks"][0]["lines"][0][0]
    assert {"text", "size", "font", "color", "bold", "italic"} <= set(sp)
    assert el["drawings"], "should capture vector drawings"


def test_build_drawings_line_and_rect(tmp_path):
    p = str(tmp_path / "s.pdf"); _pdf_with_shapes(p)
    doc = fitz.open(p); dr = build_drawings(doc[0]); doc.close()
    assert dr
    assert all(d.get("d") for d in dr)            # mỗi path có chuỗi "d"
    assert any(d.get("stroke") for d in dr)       # line/rect có viền


def test_render_blocks_page_is_relative_with_vector(tmp_path):
    p = str(tmp_path / "s.pdf"); _pdf_with_shapes(p)
    doc = fitz.open(p); el = build_blocks(doc[0]); doc.close()
    html = render_blocks_page(el)
    assert "aspect-ratio:300.00/200.00" in html   # trang responsive
    assert "cqw" in html and "%" in html          # size + vị trí tương đối
    assert "px" not in html                        # KHÔNG còn absolute px
    assert '<svg class="vec"' in html              # lớp vector


def test_render_escapes_text():
    el = {"page_w": 100, "page_h": 100, "images": [], "drawings": [],
          "blocks": [{"bbox": [0, 0, 50, 10], "lines": [[{
              "text": "a<b>&c", "size": 10, "font": "serif",
              "color": "#000", "bold": False, "italic": False}]]}]}
    html = render_blocks_page(el)
    assert "a&lt;b&gt;&amp;c" in html


def test_htmlflow_endpoint(client, db_session, tmp_path):
    from backend.app.models_db import DBDocument
    from backend.app.core import DATA_DIR
    doc_id = "hfdoc"
    raw = os.path.join(DATA_DIR, "raw_pdf"); os.makedirs(raw, exist_ok=True)
    _pdf_with_shapes(os.path.join(raw, f"{doc_id}.pdf"))
    db_session.add(DBDocument(id=doc_id, filename="s.pdf", total_pages=1, status="extracted"))
    db_session.commit()
    r = client.get(f"/api/docs/{doc_id}/htmlflow")
    assert r.status_code == 200
    t = r.text
    assert 'class="pf"' in t and "cqw" in t and "btb-zoom" in t and 'class="vec"' in t
    os.remove(os.path.join(raw, f"{doc_id}.pdf"))


def test_htmlflow_404_when_no_pdf(client, db_session):
    from backend.app.models_db import DBDocument
    db_session.add(DBDocument(id="nopdf", filename="x.pdf", total_pages=1, status="extracted"))
    db_session.commit()
    r = client.get("/api/docs/nopdf/htmlflow")
    assert r.status_code == 404
