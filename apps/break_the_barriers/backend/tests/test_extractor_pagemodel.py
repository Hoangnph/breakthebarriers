import os
import json
import glob
import pytest

_PDF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
       "assets", "books", "2024-wttc-introduction-to-ai.pdf"))


@pytest.mark.skipif(not os.path.exists(_PDF), reason="sample PDF not available")
def test_extractor_writes_model_json(tmp_path):
    from backend.app.services.extractor import DoclingExtractor
    out = str(tmp_path / "out")
    DoclingExtractor.extract_pdf_to_html(_PDF, out, "d")
    models = sorted(glob.glob(os.path.join(out, "d-*.model.json")))
    assert models, "no .model.json sidecar written"
    m = json.load(open(models[0], encoding="utf-8"))
    assert m["kind"] in ("text", "image", "mixed")
    assert "blocks" in m and "figures" in m
    assert m["page_w"] > 0 and m["page_h"] > 0
