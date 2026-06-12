from backend.app.services.pdf_text_extractor import blocks_from_pymupdf_dict
from backend.app.services.page_model import FontSpec


def _span(text, size=11, flags=0, color=0, font="Helvetica"):
    return {"text": text, "size": size, "flags": flags, "color": color, "font": font}


def test_groups_block_lines_into_one_block():
    raw = {"blocks": [
        {"type": 0, "bbox": [72, 40, 272, 64], "lines": [
            {"bbox": [72, 40, 272, 52], "spans": [_span("Brief history of")]},
            {"bbox": [72, 52, 272, 64], "spans": [_span("Artificial Intelligence")]},
        ]},
    ]}
    blocks = blocks_from_pymupdf_dict(raw)
    assert len(blocks) == 1
    assert blocks[0]["text"] == "Brief history of Artificial Intelligence"
    assert blocks[0]["bbox"] == [72, 40, 200, 24]
    assert isinstance(blocks[0]["font"], FontSpec)


def test_skips_image_blocks_and_empty_text():
    raw = {"blocks": [
        {"type": 1, "bbox": [0, 0, 100, 100]},
        {"type": 0, "bbox": [0, 0, 10, 10], "lines": [
            {"bbox": [0, 0, 10, 10], "spans": [_span("   ")]}]},
        {"type": 0, "bbox": [0, 0, 50, 12], "lines": [
            {"bbox": [0, 0, 50, 12], "spans": [_span("206.")]}]},
    ]}
    blocks = blocks_from_pymupdf_dict(raw)
    assert [b["text"] for b in blocks] == ["206."]


def test_bold_span_yields_weight_700():
    raw = {"blocks": [{"type": 0, "bbox": [0, 0, 80, 20], "lines": [
        {"bbox": [0, 0, 80, 20], "spans": [_span("CONTENTS", size=24, flags=16, font="Helvetica-Bold")]}]}]}
    blocks = blocks_from_pymupdf_dict(raw)
    assert blocks[0]["font"].weight == 700
    assert blocks[0]["font"].size == 24.0
