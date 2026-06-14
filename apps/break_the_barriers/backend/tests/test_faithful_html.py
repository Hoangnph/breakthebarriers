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
    # Hybrid: nền raster (class="bg") + text HTML (cqw); không còn lớp vector svg.
    assert 'class="pf"' in t and "cqw" in t and "btb-zoom" in t and 'class="bg"' in t
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


def test_css_color_alpha():
    from backend.app.services.faithful_html_renderer import _css_color
    assert _css_color("#ff0000", 255) == "#ff0000"
    assert _css_color("#ff0000", 128).startswith("rgba(255,0,0,")


def test_extract_alpha_rotation_opacity_from_pdf(tmp_path):
    """PDF có chữ mờ + chữ xoay 90° + nền trong suốt → trích đúng."""
    p = str(tmp_path / "sp.pdf")
    doc = fitz.open(); pg = doc.new_page(width=220, height=220)
    pg.insert_text((20, 60), "faint red", fontsize=12, color=(1, 0, 0), fill_opacity=0.35)
    pg.insert_text((30, 200), "rotated", fontsize=12, rotate=90)
    pg.draw_rect(fitz.Rect(10, 10, 120, 30), fill=(1, 1, 0), fill_opacity=0.4)
    doc.save(p); doc.close()
    doc = fitz.open(p); el = build_blocks(doc[0]); doc.close()
    alphas = [s["alpha"] for b in el["blocks"] for ln in b["lines"] for s in ln["spans"]]
    rots = [ln["rot"] for b in el["blocks"] for ln in b["lines"]]
    assert any(a < 255 for a in alphas)                        # chữ mờ
    assert any(abs(r) > 45 for r in rots)                       # chữ xoay
    assert any(d["fill_opacity"] < 1 for d in el["drawings"])   # nền trong suốt


def test_render_alpha_and_rotation_relative():
    from backend.app.services.faithful_html_renderer import render_analyzed_page
    el = {"page_w": 200, "page_h": 200, "images": [],
          "drawings": [{"d": "M0 0H50V50H0Z", "fill": "#ffff00", "stroke": None,
                        "width": 0, "fill_opacity": 0.4, "stroke_opacity": 1.0}],
          "blocks": [
              {"bbox": [10, 80, 80, 12], "lines": [{"bbox": [10, 80, 80, 12], "rot": 0.0, "wmode": 0,
                  "spans": [{"text": "faint", "size": 10, "font": "sans-serif",
                             "color": "#ff0000", "alpha": 89, "bold": False, "italic": False}]}]},
              {"bbox": [10, 100, 12, 80], "lines": [{"bbox": [10, 100, 12, 80], "rot": -90.0, "wmode": 0,
                  "spans": [{"text": "vert", "size": 10, "font": "sans-serif",
                             "color": "#0000ff", "alpha": 255, "bold": False, "italic": False}]}]},
          ]}
    html = render_analyzed_page(analyze_layout(el))
    assert "rgba(255,0,0," in html                             # chữ mờ
    assert 'fill-opacity="0.4' in html                          # nền trong suốt
    assert "rotate(-90" in html and "translate(-50%,-50%)" in html  # xoay quanh tâm


def test_image_clip_intersection():
    from backend.app.services.text_layer import _image_clip
    assert _image_clip([0, 0, 600, 300], [[0, 0, 600, 190]], 600, 800) == [0, 0, 600, 190]
    assert _image_clip([0, 0, 600, 300], [[0, 0, 600, 800]], 600, 800) is None   # clip full → bỏ


def test_soften_overlay_over_image():
    from backend.app.services.text_layer import _soften_overlays
    images = [{"bbox": [0, 0, 600, 800], "order": 1}]
    draws = [{"fill": "#000000", "rect": [0, 0, 600, 800], "order": 5, "fill_opacity": 1.0}]
    _soften_overlays(images, draws)
    assert draws[0]["fill_opacity"] <= 0.5                       # overlay phủ ảnh → mờ
    images2 = [{"bbox": [0, 0, 600, 800], "order": 1}]
    panel = [{"fill": "#ffffff", "rect": [0, 400, 300, 700], "order": 5, "fill_opacity": 1.0}]
    _soften_overlays(images2, panel)
    assert panel[0]["fill_opacity"] == 1.0                      # panel nhỏ → giữ đặc


def test_render_interleaves_paint_z_order():
    from backend.app.services.faithful_html_renderer import render_analyzed_page
    t = {"page_w": 100, "page_h": 100, "sections": [],
         "images": [{"bbox": [0, 0, 100, 100], "name": "bg.png", "order": 5, "clip": None}],
         "drawings": [{"d": "M0 0H100V100H0Z", "fill": "#ffffff", "stroke": None,
                       "width": 0, "fill_opacity": 1.0, "stroke_opacity": 1.0,
                       "rect": [0, 0, 100, 100], "order": 10}]}
    html = render_analyzed_page(t)
    assert html.index("<img") < html.index("<svg")             # panel (order 10) vẽ SAU ảnh


def test_render_clipped_image_uses_overflow_container():
    from backend.app.services.faithful_html_renderer import render_analyzed_page
    t = {"page_w": 200, "page_h": 200, "sections": [], "drawings": [],
         "images": [{"bbox": [0, 0, 200, 120], "name": "b.png", "order": 1,
                     "clip": [0, 0, 200, 60]}]}
    html = render_analyzed_page(t)
    assert "overflow:hidden" in html and "<img" in html        # crop bằng container


def test_save_pdf_image_applies_smask(tmp_path):
    """Ảnh có vùng trong suốt → PNG xuất ra phải có kênh alpha (không nền đen)."""
    from PIL import Image
    from backend.app.services.text_layer import save_pdf_image
    img = Image.new("RGBA", (40, 20), (255, 0, 0, 0))           # phải: trong suốt
    for x in range(20):
        for y in range(20):
            img.putpixel((x, y), (255, 0, 0, 255))              # trái: đỏ đặc
    ip = str(tmp_path / "a.png"); img.save(ip)
    doc = fitz.open(); pg = doc.new_page(width=100, height=100)
    pg.insert_image(fitz.Rect(10, 10, 90, 50), filename=ip)
    pp = str(tmp_path / "d.pdf"); doc.save(pp); doc.close()
    doc = fitz.open(pp)
    xref = doc.get_page_images(0)[0][0]
    op = str(tmp_path / "out.png")
    assert save_pdf_image(doc, xref, op)
    doc.close()
    assert "A" in Image.open(op).getbands()                     # có alpha


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


def test_block_source_text_joins_spans():
    from backend.app.services.faithful_html_renderer import block_source_text
    blk = {"lines": [{"spans": [{"text": "Hello"}, {"text": "world"}]},
                     {"spans": [{"text": "friend"}]}]}
    assert block_source_text(blk) == "Hello world friend"


def test_render_dich_block_mode_vs_goc_line_mode():
    from backend.app.services.faithful_html_renderer import render_analyzed_page, block_source_text
    blk = {"bbox": [10, 10, 120, 30],
           "lines": [{"bbox": [10, 10, 120, 12], "spans": [{
               "text": "Hello world", "size": 10, "font": "sans-serif",
               "color": "#000000", "bold": False, "italic": False}]}]}
    t = {"page_w": 200, "page_h": 200, "bg": "x.jpg", "images": [], "drawings": [],
         "sections": [{"kind": "full", "bbox": [10, 10, 120, 30], "blocks": [blk]}]}
    src = block_source_text(blk)
    # Dịch (lang_map) → block .tb có bản dịch, không có .ln
    dich = render_analyzed_page(t, "", {src: "Xin chào thế giới"})
    assert 'class="tb"' in dich and "Xin chào thế giới" in dich and 'class="ln"' not in dich
    # Gốc (no lang_map) → per-line .ln, không .tb
    goc = render_analyzed_page(t, "")
    assert 'class="ln"' in goc and 'class="tb"' not in goc


def test_perform_translate_flow_via_harness(db_session, monkeypatch):
    from backend.app.core import DATA_DIR
    from backend.app.models_db import DBDocument
    from backend.app.routers.documents import _perform_translate_flow
    from backend.app.services import translation_harness as TH
    from backend.app.services.translator_v2 import TranslatorV2

    doc_id = "tflowdoc"
    raw = os.path.join(DATA_DIR, "raw_pdf"); os.makedirs(raw, exist_ok=True)
    d = fitz.open(); pg = d.new_page(width=300, height=200)
    pg.insert_text((20, 40), "Artificial Intelligence here", fontsize=12)
    d.save(os.path.join(raw, f"{doc_id}.pdf")); d.close()
    db_session.add(DBDocument(id=doc_id, filename="d.pdf", total_pages=1, status="extracted"))
    db_session.commit()
    # harness mock → winner + score (không gọi Gemini)
    monkeypatch.setattr(TH.TranslationHarness, "harmonize_page",
                        staticmethod(lambda bh, *a: (["Trí tuệ nhân tạo"] * len(bh), [95] * len(bh))))
    res = _perform_translate_flow(doc_id, "vi", "max", db_session, max_pages=1)
    assert res["status"] == "done" and res["translated_blocks"] >= 1
    # TM được lưu theo source text block → Dịch view đọc được
    from backend.app.services.faithful_html_renderer import block_source_text
    import fitz as _f
    fd = _f.open(os.path.join(raw, f"{doc_id}.pdf")); el = build_blocks(fd[0]); fd.close()
    src = block_source_text(el["blocks"][0])
    assert TranslatorV2.tm_lookup(src, "vi", db_session) == "Trí tuệ nhân tạo"
    os.remove(os.path.join(raw, f"{doc_id}.pdf"))


def test_render_translated_reflow_justified_headings():
    from backend.app.services.faithful_html_renderer import render_translated_reflow, block_source_text
    head = {"bbox": [10, 10, 200, 30], "lines": [{"bbox": [10, 10, 200, 24], "spans": [{
        "text": "Big Heading", "size": 24.0, "font": "sans-serif", "color": "#000",
        "bold": True, "italic": False}]}]}
    body = {"bbox": [10, 50, 200, 80], "lines": [{"bbox": [10, 50, 200, 12], "spans": [{
        "text": "Body sentence here", "size": 10.0, "font": "sans-serif", "color": "#000",
        "bold": False, "italic": False}]}]}
    t = {"page_w": 300, "page_h": 400, "images": [],
         "sections": [{"kind": "full", "bbox": [10, 10, 200, 120], "blocks": [head, body]}]}
    lm = {block_source_text(head): "Tiêu Đề Lớn", block_source_text(body): "Câu nội dung dịch"}
    html = render_translated_reflow([t], lm)
    assert "<h2" in html and "Tiêu Đề Lớn" in html             # heading
    assert "<p" in html and "Câu nội dung dịch" in html        # body
    assert "text-align:justify" in html                         # justified
    assert 'class="dp"' in html                                 # trang reflow


def test_reflow_band_two_columns_and_image():
    from backend.app.services.faithful_html_renderer import render_translated_reflow
    blkL = {"bbox": [10, 60, 80, 20], "lines": [{"bbox": [10, 60, 80, 12], "spans": [
        {"text": "left", "size": 10.0, "font": "s", "color": "#000", "bold": False, "italic": False}]}]}
    blkR = {"bbox": [110, 60, 80, 20], "lines": [{"bbox": [110, 60, 80, 12], "spans": [
        {"text": "right", "size": 10.0, "font": "s", "color": "#000", "bold": False, "italic": False}]}]}
    t = {"page_w": 300, "page_h": 400,
         "images": [{"bbox": [10, 10, 180, 40], "name": "p.png"}],
         "sections": [{"kind": "band", "bbox": [10, 60, 180, 30],
                       "columns": [{"bbox": [10, 60, 80, 20], "blocks": [blkL]},
                                   {"bbox": [110, 60, 80, 20], "blocks": [blkR]}]}]}
    html = render_translated_reflow([t], {})
    assert 'class="band"' in html and html.count('class="bcol"') == 2   # 2 cột
    assert "<figure>" in html and "p.png" in html                       # ảnh inline


def test_is_design_page_detects_full_bleed_image():
    from backend.app.services.faithful_html_renderer import is_design_page
    # ảnh phủ ~full trang → design
    design = {"page_w": 200, "page_h": 300, "sections": [],
              "images": [{"bbox": [0, 0, 200, 290]}]}
    assert is_design_page(design) is True
    # ảnh nhỏ (diagram) → không design
    content = {"page_w": 200, "page_h": 300, "sections": [],
               "images": [{"bbox": [10, 10, 80, 40]}]}
    assert is_design_page(content) is False


def test_render_dich_mixed_picks_mode_per_page():
    from backend.app.services.faithful_html_renderer import render_dich_mixed
    blk = {"bbox": [10, 10, 120, 20], "lines": [{"bbox": [10, 10, 120, 12], "spans": [{
        "text": "Hi", "size": 10.0, "font": "s", "color": "#000", "bold": False, "italic": False}]}]}
    design = {"page_w": 200, "page_h": 200, "bg": "bg.jpg", "images": [], "drawings": [],
              "sections": [{"kind": "full", "bbox": [10, 10, 120, 20], "blocks": [blk]}]}
    content = {"page_w": 200, "page_h": 200, "images": [], "drawings": [],
               "sections": [{"kind": "full", "bbox": [10, 10, 120, 20], "blocks": [blk]}]}
    html = render_dich_mixed([design, content], {})
    assert 'class="pf"' in html      # design page → positioned
    assert 'class="dp"' in html      # content page → reflow


def test_translated_design_block_grows_to_room_not_crammed():
    """Trang design: block dịch (tiêu đề hero) KHÔNG bị khóa vào chiều cao hộp
    tiếng Anh + co nhỏ. Box dùng height = khoảng trống tới đáy trang (cqw cố định
    → clientHeight ổn định cho fitTB) → giữ cỡ chữ lớn như gốc, chỉ co khi text
    thật sự vượt khoảng trống."""
    # Tiêu đề ở top trang cao → còn nhiều chỗ phía dưới.
    title = {"bbox": [100, 100, 400, 60],
             "lines": [{"bbox": [100, 100, 400, 60], "spans": [{
                 "text": "Title EN", "size": 80.0, "color": "#ffffff",
                 "font": "Arial", "bold": True, "italic": False}]}]}
    t = {"page_w": 1000, "page_h": 1400, "images": [], "drawings": [], "bg": None,
         "sections": [{"kind": "full", "role": "", "bbox": [100, 100, 400, 60],
                       "blocks": [title]}]}
    lang_map = {"Title EN": "TIÊU ĐỀ TIẾNG VIỆT DÀI HƠN RẤT NHIỀU SO VỚI GỐC"}
    html = render_analyzed_page(t, lang_map=lang_map)
    # box cao = khoảng trống tới đáy: (1400-100)/1000*100 = 130cqw (KHÔNG 6%)
    assert "height:130.000cqw" in html
    assert "overflow:hidden" in html  # vẫn cắt nếu thật sự tràn khoảng trống
    # giữ cỡ chữ gốc 80/1000*100 = 8cqw (không hạ sẵn ở server → fitTB co khi cần)
    assert "font-size:8.000cqw" in html
    # cỡ gốc LƯU ở data-fs để fitTB reset về ĐÚNG cỡ (KHÔNG xóa về inherit 16px)
    assert 'data-fs="8.000cqw"' in html


def test_translated_design_block_room_stops_at_next_block_no_overlap():
    """Tiêu đề hero KHÔNG được tràn đè phụ đề bên dưới: room (chiều cao box) =
    khoảng cách tới TOP của block kế dưới, không phải tới đáy trang → fitTB co vừa
    khoảng trống đó, hai block không chồng nhau (vd bìa: title + subtitle)."""
    title = {"bbox": [100, 100, 400, 60],
             "lines": [{"bbox": [100, 100, 400, 60], "spans": [{
                 "text": "Title EN", "size": 80.0, "color": "#fff",
                 "font": "Arial", "bold": True, "italic": False}]}]}
    subtitle = {"bbox": [100, 400, 400, 30],
                "lines": [{"bbox": [100, 400, 400, 30], "spans": [{
                    "text": "Sub EN", "size": 30.0, "color": "#fff",
                    "font": "Arial", "bold": False, "italic": False}]}]}
    t = {"page_w": 1000, "page_h": 1400, "images": [], "drawings": [], "bg": None,
         "sections": [
             {"kind": "full", "role": "", "bbox": [100, 100, 400, 60], "blocks": [title]},
             {"kind": "full", "role": "", "bbox": [100, 400, 400, 30], "blocks": [subtitle]}]}
    lang_map = {"Title EN": "TIÊU ĐỀ DÀI", "Sub EN": "PHỤ ĐỀ DÀI"}
    html = render_analyzed_page(t, lang_map=lang_map)
    # title room = next_top(400) - by(100) = 300 → 300/1000*100 = 30cqw (KHÔNG 130)
    assert "height:30.000cqw" in html
    assert "height:130.000cqw" not in html


def test_split_toc_entries():
    """Tách block TOC gộp nhiều mục 'tiêu đề … số' → list (title, num)."""
    from backend.app.services.faithful_html_renderer import _split_toc_entries
    txt = "LỜI NÓI ĐẦU.........3 GIỚI THIỆU......4 Thuật toán : Bộ não của AI\t 8"
    out = _split_toc_entries(txt)
    assert [n for _, n in out] == ["3", "4", "8"]
    assert out[0][0] == "LỜI NÓI ĐẦU"
    assert out[2][0] == "Thuật toán : Bộ não của AI"
    # văn xuôi bình thường (không leader chấm/tab) → KHÔNG nhận nhầm là TOC
    assert _split_toc_entries("Câu này kết thúc bằng số 5") == []


def test_toc_block_renders_dotted_leader_rows():
    """Block dịch chứa nhiều mục TOC → mỗi mục 1 hàng: tiêu đề + dotted leader +
    số trang canh phải (class te/tt/tl/tn), KHÔNG còn 1 đoạn dính số lộn xộn."""
    blk = {"bbox": [50, 100, 500, 30], "lines": [{"bbox": [50, 100, 500, 30], "spans": [{
        "text": "FOREWORD", "size": 10.0, "color": "#003", "font": "Arial",
        "bold": False, "italic": False}]}]}
    t = {"page_w": 600, "page_h": 800, "images": [], "drawings": [], "bg": None,
         "sections": [{"kind": "full", "role": "", "bbox": [50, 100, 500, 30],
                       "blocks": [blk]}]}
    lang_map = {"FOREWORD": "LỜI NÓI ĐẦU.........3 GIỚI THIỆU......4 Thuật toán\t 8"}
    html = render_analyzed_page(t, lang_map=lang_map)
    assert 'class="tb toc"' in html
    assert html.count('class="te"') == 3        # 3 hàng mục
    assert 'class="tl"' in html                  # dotted leader
    assert 'class="tn">3<' in html and 'class="tn">8<' in html  # số canh phải
    assert "LỜI NÓI ĐẦU" in html


def test_toc_leader_css_present():
    from backend.app.services.faithful_html_renderer import _FLOW_CSS
    assert ".tb.toc" in _FLOW_CSS and "dotted" in _FLOW_CSS


def test_fit_script_is_layout_stable_and_guarded():
    """fitTB không được co chữ khi layout/cqw chưa ổn định (clientHeight tí xíu)
    → phải có guard ngưỡng clientHeight; và phải lên lịch chạy lại sau khi layout
    settle (requestAnimationFrame) để phục hồi cỡ chữ nếu lần đầu chạy quá sớm."""
    from backend.app.services.faithful_html_renderer import _FIT_SCRIPT
    # guard: bỏ qua khi clientHeight quá nhỏ (layout chưa sẵn) → không over-shrink
    assert "clientHeight>" in _FIT_SCRIPT
    # chạy lại sau layout ổn định (idempotent, reset rồi mới co)
    assert "requestAnimationFrame" in _FIT_SCRIPT
    # reset cỡ chữ về data-fs (cỡ gốc inline) — KHÔNG xóa '' (sẽ về inherit 16px)
    assert "data-fs" in _FIT_SCRIPT
