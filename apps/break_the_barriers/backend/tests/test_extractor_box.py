import os
import json
import pytest

_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
       "assets", "books", "2024-wttc-introduction-to-ai.pdf"))


@pytest.mark.skipif(not os.path.exists(_PDF), reason="sample PDF not available")
def test_extractor_writes_per_block_box(tmp_path):
    from backend.app.services.extractor import DoclingExtractor
    out = str(tmp_path / "out")
    DoclingExtractor.extract_pdf_to_html(_PDF, out, "bx")
    # Page 2 (CONTENTS over photo) is image/mixed with a raster -> blocks get box.
    m = json.load(open(os.path.join(out, "bx-2.model.json"), encoding="utf-8"))
    boxed = [b for b in m["blocks"] if b.get("box")]
    assert boxed, "no block has a box"
    modes = {b["box"]["mode"] for b in boxed}
    assert modes <= {"fill", "scrim"}
    assert all(b["box"].get("fill") for b in boxed)
