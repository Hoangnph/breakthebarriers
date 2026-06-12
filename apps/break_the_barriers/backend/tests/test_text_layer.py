import fitz
from backend.app.services.text_layer import build_text_layer, reflow_blocks


def test_build_text_layer_returns_positioned_spans(sample_pdf):
    doc = fitz.open(sample_pdf)
    layer = build_text_layer(doc[0])
    doc.close()
    assert layer["page_w"] == 400 and layer["page_h"] == 300
    texts = " ".join(s["text"] for s in layer["spans"])
    assert "Hello World Heading" in texts
    for s in layer["spans"]:
        x, y, w, h = s["bbox"]
        assert w > 0 and h > 0 and x >= 0 and y >= 0


def test_reflow_blocks_tags_heading_by_font_size(sample_pdf):
    doc = fitz.open(sample_pdf)
    blocks = reflow_blocks(doc[0])
    doc.close()
    assert blocks, "reflow_blocks should return ordered text blocks"
    heading = next(b for b in blocks if "Heading" in b["text"])
    assert heading["role"] == "heading"
    body = next(b for b in blocks if "body paragraph" in b["text"])
    assert body["role"] == "body"
