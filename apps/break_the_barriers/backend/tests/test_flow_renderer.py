from backend.app.services.flow_model import FlowElement
from backend.app.services.flow_renderer import render_flow_html


def test_renders_semantic_tags_with_translations():
    flow = [FlowElement(kind="heading", span_id="h", level=1),
            FlowElement(kind="paragraph", span_id="p"),
            FlowElement(kind="figure", src="f.png"),
            FlowElement(kind="image_block", src="cover.clean.png")]
    html = render_flow_html(flow, {"h": "Tiêu đề", "p": "Đoạn văn"},
                            image_url_base="http://api/assets")
    assert "<h1" in html and "Tiêu đề" in html
    assert "<p" in html and "Đoạn văn" in html
    assert 'data-span="h"' in html and 'data-span="p"' in html
    assert 'class="fl-fig" src="http://api/assets/f.png"' in html
    assert 'class="fl-page" src="http://api/assets/cover.clean.png"' in html


def test_skips_text_without_translation():
    flow = [FlowElement(kind="paragraph", span_id="x")]
    html = render_flow_html(flow, {}, image_url_base="http://api/a")
    assert 'data-span="x"' not in html


def test_escapes_text():
    flow = [FlowElement(kind="paragraph", span_id="p")]
    html = render_flow_html(flow, {"p": "a < b & c"}, image_url_base="http://api/a")
    assert "a &lt; b &amp; c" in html
