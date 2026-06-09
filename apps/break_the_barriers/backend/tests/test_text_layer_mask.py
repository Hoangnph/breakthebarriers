from backend.app.services.text_layer_renderer import _opaque_fill, _mask_css


def test_opaque_fill_raises_low_alpha():
    assert _opaque_fill("rgba(255,255,255,0.55)") == "rgba(255,255,255,0.9)"


def test_opaque_fill_keeps_high_alpha():
    assert _opaque_fill("rgba(0,0,0,0.95)") == "rgba(0,0,0,0.95)"


def test_opaque_fill_passes_hex_through():
    assert _opaque_fill("#010203") == "#010203"


def test_mask_css_scrim_has_padding():
    css = _mask_css({"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    assert "background:rgba(255,255,255,0.9)" in css
    assert "padding:0 2px" in css


def test_mask_css_fill_no_padding():
    assert _mask_css({"mode": "fill", "fill": "#010203"}) == "background:#010203;"


def test_mask_css_empty_without_fill():
    assert _mask_css(None) == ""
    assert _mask_css({"mode": "scrim"}) == ""


def test_text_page_always_draws_raster_and_masks():
    from backend.app.services.page_model import PageModel, Block, FontSpec
    from backend.app.services.text_layer_renderer import render_text_layer
    blk = Block(span_id="s1", role="body", bbox=[72, 100, 300, 40], text="",
                font=FontSpec(size=11, weight=400, italic=False, color="#000000",
                              align="left", family_class="sans"),
                box={"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    pm = PageModel(page_w=595, page_h=842, kind="text",
                   background={"color": "#ffffff", "image": None},
                   blocks=[blk], figures=[], page_class="text", cover="none", page_num=38)
    html = render_text_layer(pm, {"s1": "đoạn dịch"}, "http://x/assets")
    assert '<img class="tl-bg" src="http://x/assets/page-38.png"' in html
    assert "đoạn dịch" in html
    assert "background:rgba(255,255,255,0.9)" in html
