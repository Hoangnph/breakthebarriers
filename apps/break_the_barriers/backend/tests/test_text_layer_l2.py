from backend.app.services.page_model import FontSpec, Block, PageModel
from backend.app.services.text_layer_renderer import render_text_layer


def _img_model(box=None):
    return PageModel(
        page_w=595.0, page_h=842.0, kind="mixed",
        background={"color": "#000", "image": "page-2.png"},
        blocks=[Block("s1", "heading", [72, 40, 200, 24], "x",
                      FontSpec(24, 700, False, "#fff", "left", "sans"), box=box)],
        figures=[],
    )


def test_raster_background_rendered_when_image_present():
    html = render_text_layer(_img_model(), {"s1": "DỊCH"}, "http://api/assets")
    assert 'class="tl-bg"' in html
    assert "http://api/assets/page-2.png" in html
    assert "DỊCH" in html


def test_block_fill_box_applies_solid_background():
    html = render_text_layer(_img_model({"mode": "fill", "fill": "#ffffff"}),
                             {"s1": "X"}, "http://api/assets")
    assert "#ffffff" in html


def test_block_scrim_box_applies_rgba_background():
    html = render_text_layer(_img_model({"mode": "scrim", "fill": "rgba(0,0,0,0.45)"}),
                             {"s1": "X"}, "http://api/assets")
    assert "rgba(0,0,0,0.45)" in html


def test_text_page_unchanged_no_raster():
    m = PageModel(595.0, 842.0, "text", {"color": "#fff", "image": None},
                  [Block("s1", "body", [10, 10, 100, 20], "x",
                         FontSpec(11, 400, False, "#111", "left", "sans"))], [])
    html = render_text_layer(m, {"s1": "Y"}, "http://api/assets")
    assert 'class="tl-bg"' not in html
    assert "Y" in html
