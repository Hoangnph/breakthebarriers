import os
import json
from backend.app.services.faithful_extractor import FaithfulExtractor


def test_extract_pdf_writes_three_sidecars(sample_pdf, tmp_path, monkeypatch):
    # Ép Docling tắt → dùng reflow_blocks (nhanh, xác định)
    monkeypatch.setattr(FaithfulExtractor, "_docling_structure", staticmethod(lambda p: None))
    out_dir = str(tmp_path / "out")
    html_files = FaithfulExtractor.extract_pdf(sample_pdf, out_dir, "docX")

    assert len(html_files) == 1
    base = os.path.join(out_dir, "docX-1")

    assert os.path.exists(base + ".svg")
    assert "<svg" in open(base + ".svg", encoding="utf-8").read()

    tl = json.load(open(base + ".textlayer.json", encoding="utf-8"))
    assert tl["spans"] and len(tl["spans"][0]["bbox"]) == 4

    html = open(base + ".html", encoding="utf-8").read()
    assert 'id="s1"' in html
    assert "Hello World Heading" in html


def test_render_visual_falls_back_to_jpg_on_svg_error(sample_pdf, tmp_path, monkeypatch):
    import fitz
    doc = fitz.open(sample_pdf)
    page = doc[0]

    def boom():
        raise RuntimeError("svg fail")
    monkeypatch.setattr(page, "get_svg_image", boom)

    name = FaithfulExtractor._render_visual(page, str(tmp_path), "docY", 1)
    doc.close()
    assert name == "docY-1.jpg"
    assert os.path.exists(os.path.join(str(tmp_path), name))


def test_extract_pdf_guards_per_page_failure(sample_pdf, tmp_path, monkeypatch):
    # 1 trang lỗi → placeholder, không abort cả doc; vẫn trả .html giữ alignment.
    import backend.app.services.faithful_extractor as fe
    monkeypatch.setattr(fe.FaithfulExtractor, "_docling_structure", staticmethod(lambda p: None))

    def boom(_page):
        raise RuntimeError("textlayer fail")
    monkeypatch.setattr(fe, "build_text_layer", boom)

    out_dir = str(tmp_path / "out")
    html_files = fe.FaithfulExtractor.extract_pdf(sample_pdf, out_dir, "docZ")
    assert len(html_files) == 1                      # không abort
    html = open(html_files[0], encoding="utf-8").read()
    assert 'id="s1"' in html and "[page 1]" in html  # placeholder có span để pipeline dịch không vỡ
