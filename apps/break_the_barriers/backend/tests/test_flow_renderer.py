import re as _re

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


def test_headings_wrapped_in_sections():
    flow = [FlowElement(kind="heading", span_id="h", level=1),
            FlowElement(kind="paragraph", span_id="p")]
    html = render_flow_html(flow, {"h": "Chương 1", "p": "Nội dung"},
                            image_url_base="http://api/a")
    assert '<section id="sec-h">' in html
    seg = html.split('<section id="sec-h">', 1)[1]
    assert "Chương 1" in seg and "Nội dung" in seg


def test_pre_heading_content_in_intro_section():
    flow = [FlowElement(kind="paragraph", span_id="p0"),
            FlowElement(kind="heading", span_id="h", level=1)]
    html = render_flow_html(flow, {"p0": "Mở đầu", "h": "Chương"},
                            image_url_base="http://api/a")
    assert '<section class="fl-intro">' in html
    assert '<section id="sec-h">' in html
    assert html.count("<section") == html.count("</section>")


def test_generated_contents_links_to_headings_and_suppresses_original_toc():
    flow = [FlowElement(kind="heading", span_id="a", level=1),
            FlowElement(kind="heading", span_id="b", level=2),
            FlowElement(kind="paragraph", span_id="toc1")]
    html = render_flow_html(
        flow, {"a": "Phần A", "b": "Phần B", "toc1": "Phần A......3"},
        image_url_base="http://api/a")
    assert '<nav class="fl-contents">' in html
    assert 'href="#sec-a"' in html and 'href="#sec-b"' in html
    assert "Phần A" in html and "Phần B" in html
    assert "......" not in html
    assert "Phần A......3" not in html   # raw original TOC entry text suppressed


def test_every_contents_link_has_matching_section():
    flow = [FlowElement(kind="heading", span_id="a", level=1),
            FlowElement(kind="heading", span_id="b", level=1),
            FlowElement(kind="paragraph", span_id="t")]
    html = render_flow_html(flow, {"a": "A", "b": "B", "t": "A....1"},
                            image_url_base="http://api/a")
    hrefs = set(_re.findall(r'href="#(sec-[^"]+)"', html))
    ids = set(_re.findall(r'<section id="(sec-[^"]+)"', html))
    assert hrefs and hrefs <= ids


def test_no_toc_page_no_contents_block():
    flow = [FlowElement(kind="heading", span_id="h", level=1),
            FlowElement(kind="paragraph", span_id="p")]
    html = render_flow_html(flow, {"h": "H", "p": "Đoạn thường."},
                            image_url_base="http://api/a")
    # "Đoạn thường." ends in a period, not dots+number → not a TOC entry
    assert 'class="fl-contents"' not in html
    assert '<section id="sec-h">' in html


def test_toc_entry_not_dropped_when_no_headings():
    # A TOC-shaped paragraph but zero headings: must NOT be silently dropped.
    flow = [FlowElement(kind="paragraph", span_id="p")]
    html = render_flow_html(flow, {"p": "Phần A......3"},
                            image_url_base="http://api/a")
    assert 'class="fl-contents"' not in html      # no nav (no headings)
    assert "Phần A" in html                        # content preserved
    assert '<p data-span="p">' in html             # rendered as a paragraph


def test_list_item_has_li_class_and_css():
    flow = [FlowElement(kind="list", span_id="x")]
    html = render_flow_html(flow, {"x": "Mục một"}, image_url_base="http://api/a")
    assert '<p class="li" data-span="x">' in html
    assert ".fl-doc p.li" in html


def test_flow_html_has_zoom_listener():
    html = render_flow_html([FlowElement(kind="paragraph", span_id="p")],
                            {"p": "x"}, image_url_base="http://api/a")
    assert "btb-zoom" in html
    assert "documentElement.style.fontSize" in html
    assert "addEventListener('message'" in html
    # script sits inside the body, after the article
    assert html.index("fl-doc") < html.index("btb-zoom") < html.index("</body>")
