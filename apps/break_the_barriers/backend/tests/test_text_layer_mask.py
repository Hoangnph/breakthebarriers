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
