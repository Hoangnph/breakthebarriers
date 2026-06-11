import os
import fitz
from backend.app.services.text_layer import build_blocks, build_drawings
from backend.app.services.layout_analyzer import analyze_layout
from backend.app.services.faithful_html_renderer import render_analyzed_page


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
    line0 = el["blocks"][0]["lines"][0]
    assert "bbox" in line0 and len(line0["bbox"]) == 4   # line có bbox để định vị
    sp = line0["spans"][0]
    assert {"text", "size", "font", "color", "bold", "italic"} <= set(sp)
    assert el["drawings"], "should capture vector drawings"


def test_build_drawings_line_and_rect(tmp_path):
    p = str(tmp_path / "s.pdf"); _pdf_with_shapes(p)
    doc = fitz.open(p); dr = build_drawings(doc[0]); doc.close()
    assert dr
    assert all(d.get("d") for d in dr)            # mỗi path có chuỗi "d"
    assert any(d.get("stroke") for d in dr)       # line/rect có viền


def test_render_analyzed_page_is_relative_with_vector(tmp_path):
    p = str(tmp_path / "s.pdf"); _pdf_with_shapes(p)
    doc = fitz.open(p); el = build_blocks(doc[0]); doc.close()
    html = render_analyzed_page(analyze_layout(el))
    assert "aspect-ratio:300.00/200.00" in html   # trang responsive
    assert "cqw" in html and "%" in html          # size + vị trí tương đối
    assert "px" not in html                        # KHÔNG còn absolute px
    assert '<svg class="vec"' in html              # lớp vector


def test_render_escapes_text():
    el = {"page_w": 100, "page_h": 100, "images": [], "drawings": [],
          "blocks": [{"bbox": [0, 0, 50, 10], "lines": [{"bbox": [0, 0, 50, 10], "spans": [{
              "text": "a<b>&c", "size": 10, "font": "serif",
              "color": "#000", "bold": False, "italic": False}]}]}]}
    html = render_analyzed_page(analyze_layout(el))
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


def _blk(x, y, w, h, text):
    return {"bbox": [x, y, w, h], "lines": [{"bbox": [x, y, w, h], "spans": [{
        "text": text, "size": 10, "font": "sans-serif",
        "color": "#000000", "bold": False, "italic": False}]}]}


def _two_col_el():
    """el thủ công (không qua PyMuPDF grouping): title full-width + 2 cột tách bbox."""
    return {"page_w": 600, "page_h": 400, "images": [], "drawings": [],
            "blocks": [
                _blk(40, 30, 500, 24, "Full Width Title"),   # full-width
                _blk(40, 90, 180, 120, "left column body"),  # cột trái
                _blk(360, 90, 180, 120, "right column body"),  # cột phải
            ]}


def test_analyze_detects_band_and_columns():
    from backend.app.services.layout_analyzer import analyze_layout
    t = analyze_layout(_two_col_el())
    kinds = [s["kind"] for s in t["sections"]]
    assert "band" in kinds, f"expected a multi-column band, got {kinds}"
    band = next(s for s in t["sections"] if s["kind"] == "band")
    assert len(band["columns"]) >= 2
    assert "full" in kinds                      # full-width title section


def test_render_analyzed_page_nests_relative():
    from backend.app.services.layout_analyzer import analyze_layout
    from backend.app.services.faithful_html_renderer import render_analyzed_page
    html = render_analyzed_page(analyze_layout(_two_col_el()))
    assert 'class="sec"' in html and 'class="col"' in html and 'class="bk"' in html
    assert "cqw" in html and "%" in html
    assert "px" not in html                      # toàn relative


def test_effective_size_from_glyph_bbox():
    """Trích font-size từ hình học glyph: bbox_h/(asc-desc). Dùng bbox khi nominal sai."""
    from backend.app.services.text_layer import _effective_size
    # nominal khớp bbox (asc-desc=1.2, bbox_h=9.6 → 8.0) → giữ nominal
    s_ok = {"size": 8.0, "bbox": [0, 0, 50, 9.6], "ascender": 0.858, "descender": -0.342}
    assert abs(_effective_size(s_ok) - 8.0) < 0.05
    # nominal SAI (size=10 nhưng glyph cao gấp đôi) → lấy cỡ THẬT từ bbox (~20)
    s_scaled = {"size": 10.0, "bbox": [0, 0, 50, 24.0], "ascender": 0.858, "descender": -0.342}
    assert _effective_size(s_scaled) > 18.0


def test_flow_includes_fit_script():
    """Flow phải kèm script co dòng khít bề rộng gốc (font web rộng/hẹp khác PDF)."""
    from backend.app.services.faithful_html_renderer import render_analyzed_flow
    html = render_analyzed_flow([analyze_layout(_two_col_el())])
    assert "scaleX(" in html and "scrollWidth" in html
    assert "transform-origin:0 0" in html       # CSS hỗ trợ scaleX từ mép trái


def test_analyze_detects_header_footer():
    from backend.app.services.layout_analyzer import analyze_layout
    el = {"page_w": 600, "page_h": 800, "images": [], "drawings": [],
          "blocks": [
              _blk(40, 20, 200, 12, "Header Left"),       # dải trên → header
              _blk(450, 20, 100, 12, "Page 1"),            # cùng hàng, bên phải
              _blk(40, 400, 400, 20, "body paragraph"),    # body
              _blk(40, 770, 300, 12, "Footer text"),       # dải dưới → footer
          ]}
    t = analyze_layout(el)
    roles = [s.get("role") for s in t["sections"]]
    assert "header" in roles and "footer" in roles
    header = next(s for s in t["sections"] if s.get("role") == "header")
    assert len(header["blocks"]) == 2            # trái + phải GIỮ trên cùng 1 hàng


def test_header_left_right_not_stacked():
    """Header trái/phải đặt CẠNH NHAU (left% khác nhau rõ) — không xếp chồng dọc."""
    import re
    from backend.app.services.layout_analyzer import analyze_layout
    from backend.app.services.faithful_html_renderer import render_analyzed_page
    el = {"page_w": 600, "page_h": 800, "images": [], "drawings": [],
          "blocks": [_blk(40, 20, 200, 12, "Left"), _blk(450, 22, 100, 12, "Right")]}
    t = analyze_layout(el)
    header = next(s for s in t["sections"] if s.get("role") == "header")
    assert len(header["blocks"]) == 2          # cùng 1 section header (1 hàng)
    html = render_analyzed_page(t)
    lefts = [float(m) for m in re.findall(r'class="bk" style="left:([0-9.]+)%', html)]
    assert len(lefts) == 2 and abs(lefts[0] - lefts[1]) > 20.0   # tách ngang → cạnh nhau
