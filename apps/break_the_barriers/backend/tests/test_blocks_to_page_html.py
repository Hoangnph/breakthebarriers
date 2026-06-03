from backend.app.services.extractor import DoclingExtractor
from backend.app.services.page_model import FontSpec


def _fs():
    return FontSpec(11, 400, False, "#111", "left", "sans")


def test_builds_html_and_blocks_with_roles():
    tagged = [
        {"text": "CONTENTS", "bbox": [10, 10, 100, 20], "font": _fs(), "role": "heading"},
        {"text": "Foreword", "bbox": [10, 40, 100, 12], "font": _fs(), "role": "list"},
        {"text": "Intro", "bbox": [10, 55, 100, 12], "font": _fs(), "role": "list"},
        {"text": "Body text here", "bbox": [10, 80, 100, 12], "font": _fs(), "role": "body"},
    ]
    html, blocks = DoclingExtractor._blocks_to_page_html(tagged, page_no=1)
    assert '<h2><span id="s1">CONTENTS</span></h2>' in html
    assert '<ul>' in html and '<li><span id="s2">Foreword</span></li>' in html
    assert '<p><span id="s4">Body text here</span></p>' in html
    assert [b["span_id"] for b in blocks] == ["s1", "s2", "s3", "s4"]
    assert blocks[0]["role"] == "heading"
    assert blocks[0]["bbox"] == [10, 10, 100, 20]
    assert blocks[0]["font"] is tagged[0]["font"]


def test_escapes_text():
    tagged = [{"text": "A & B <c>", "bbox": [0, 0, 1, 1], "font": _fs(), "role": "body"}]
    html, _ = DoclingExtractor._blocks_to_page_html(tagged, page_no=1)
    assert "A &amp; B &lt;c&gt;" in html
