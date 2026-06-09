from backend.app.services.page_model import PageModel, Block, FontSpec
from backend.app.services.faithful_flow_renderer import (
    render_faithful_page, render_faithful_flow)


def _text_page(page_num):
    blk = Block(span_id="s1", role="body", bbox=[72, 100, 300, 40], text="",
                font=FontSpec(11, 400, False, "#000000", "left", "sans"),
                box={"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    return PageModel(595.0, 842.0, "text", {"color": "#fff", "image": None}, [blk], [],
                     page_class="text", cover="none", page_num=page_num)


def test_fragment_has_aspect_and_raster_fallback():
    html = render_faithful_page(_text_page(38), {"s1": "đoạn dịch"}, "http://x/assets")
    assert 'class="ff-page"' in html
    assert "aspect-ratio:595.00/842.00" in html
    assert '<img class="ff-bg" src="http://x/assets/page-38.png"' in html


def test_fragment_overlay_text_in_cqw_with_mask():
    html = render_faithful_page(_text_page(38), {"s1": "đoạn dịch"}, "http://x/assets")
    assert "đoạn dịch" in html
    assert "cqw" in html and "data-cqw=" in html
    assert "background:rgba(255,255,255,0.9)" in html


def test_fragment_skips_blocks_without_translation_but_keeps_raster():
    html = render_faithful_page(_text_page(1), {}, "http://x/assets")
    assert 'class="ff-text"' not in html
    assert '<img class="ff-bg"' in html


def test_flow_stacks_pages_in_order_with_scripts():
    html = render_faithful_flow([_text_page(2), _text_page(1)],
                                {1: {"s1": "một"}, 2: {"s1": "hai"}}, "http://x/assets")
    assert html.count('class="ff-page"') == 2
    assert html.index('id="pg-1"') < html.index('id="pg-2"')
    assert "btb-zoom" in html and "data-cqw" in html
    assert "một" in html and "hai" in html


def test_flow_empty_pages_valid_shell():
    html = render_faithful_flow([], {}, "http://x/a")
    assert '<article class="ff-doc">' in html
    assert html.count('class="ff-page"') == 0
