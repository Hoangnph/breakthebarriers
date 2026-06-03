import os
import json
import pytest

_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
       "assets", "books", "2024-wttc-introduction-to-ai.pdf"))


@pytest.mark.skipif(not os.path.exists(_PDF), reason="sample PDF not available")
def test_pymupdf_text_source_captures_toc_and_keeps_noise_as_blocks(tmp_path):
    from backend.app.services.extractor import DoclingExtractor
    out = str(tmp_path / "out")
    DoclingExtractor.extract_pdf_to_html(_PDF, out, "ov")
    html_p2 = open(os.path.join(out, "ov-2.html"), encoding="utf-8").read()
    assert "FOREWORD" in html_p2 or "Foreword" in html_p2
    assert "Algorithms" in html_p2
    model = json.load(open(os.path.join(out, "ov-2.model.json"), encoding="utf-8"))
    assert model["blocks"], "no blocks in model"
    assert any(b.get("font") for b in model["blocks"])
