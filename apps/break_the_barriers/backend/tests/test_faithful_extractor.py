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
