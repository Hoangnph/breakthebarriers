from backend.app.services.page_model import FontSpec, Block, Figure, PageModel
from backend.app.services.page_renderer import render_page


def _text_model():
    return PageModel(595, 842, "text", {"color": "#fff", "image": None},
                     [Block("s1", "heading", [72, 40, 200, 24], "T",
                            FontSpec(24, 700, False, "#111", "left", "sans"))],
                     [])


def _image_model():
    return PageModel(595, 842, "image", {"color": "#000", "image": "page-1.png"},
                     [Block("s1", "body", [40, 700, 120, 18], "C", None)],
                     [])


def test_text_kind_uses_text_layer():
    html = render_page(_text_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="tl-page"' in html
    assert "DỊCH" in html


def test_image_kind_uses_raster_overlay():
    html = render_page(_image_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="ov-bg"' in html
    assert "page-1.png" in html
