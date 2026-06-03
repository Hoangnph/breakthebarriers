from backend.app.services.page_model import FontSpec, Block, Figure, PageModel
from backend.app.services.text_layer_renderer import render_text_layer


def _model(kind="text"):
    return PageModel(
        page_w=595.0, page_h=842.0, kind=kind,
        background={"color": "#ffffff", "image": None},
        blocks=[Block(span_id="s1", role="heading", bbox=[72, 40, 200, 24],
                      text="INTRODUCTION TO AI",
                      font=FontSpec(24, 700, False, "#1a1a1a", "left", "sans"))],
        figures=[Figure(bbox=[0, 100, 200, 150], img="d-1-fig1.png")],
    )


def test_render_uses_translated_text_not_original():
    html = render_text_layer(_model(), {"s1": "GIỚI THIỆU VỀ AI"},
                             image_url_base="http://api/assets")
    assert "GIỚI THIỆU VỀ AI" in html
    assert "INTRODUCTION TO AI" not in html


def test_render_has_no_raster_background_image():
    html = render_text_layer(_model(), {"s1": "X"}, image_url_base="http://api/assets")
    assert 'class="ov-bg"' not in html
    assert "page-1.png" not in html


def test_render_places_figure_image():
    html = render_text_layer(_model(), {"s1": "X"}, image_url_base="http://api/assets")
    assert "http://api/assets/d-1-fig1.png" in html


def test_render_applies_font_weight_and_color():
    html = render_text_layer(_model(), {"s1": "X"}, image_url_base="http://api/assets")
    assert "font-weight:700" in html
    assert "#1a1a1a" in html


def test_render_emits_fit_script_for_absolute_blocks():
    html = render_text_layer(_model(), {"s1": "X"}, image_url_base="http://api/assets")
    assert "btb-fit" in html
