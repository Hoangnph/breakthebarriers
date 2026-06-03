from backend.app.services.page_model import FontSpec, Block, PageModel
from backend.app.services.page_renderer import render_page


def _text_model():
    return PageModel(595, 842, "text", {"color": "#fff", "image": None},
                     [Block("s1", "heading", [72, 40, 200, 24], "T",
                            FontSpec(24, 700, False, "#111", "left", "sans"))],
                     [])


def _image_model():
    return PageModel(595, 842, "image", {"color": "#000", "image": "page-1.png"},
                     [Block("s1", "body", [40, 700, 120, 18], "C", None,
                            box={"mode": "scrim", "fill": "rgba(0,0,0,0.45)"})],
                     [])


def test_text_kind_uses_unified_renderer():
    html = render_page(_text_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="tl-page"' in html
    assert 'class="tl-bg"' not in html
    assert "DỊCH" in html


def test_image_kind_uses_unified_renderer_with_raster():
    html = render_page(_image_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="tl-page"' in html
    assert 'class="tl-bg"' in html
    assert "page-1.png" in html
    assert "rgba(0,0,0,0.45)" in html
    assert "DỊCH" in html
