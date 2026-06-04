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


def _two_block_model():
    return PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#ffffff", "image": None},
        blocks=[
            Block(span_id="s1", role="body", bbox=[72, 100, 200, 50],
                  text="A", font=FontSpec(11, 400, False, "#000", "left", "sans")),
            Block(span_id="s2", role="body", bbox=[72, 200, 200, 50],
                  text="B", font=FontSpec(11, 400, False, "#000", "left", "sans")),
        ],
        figures=[],
    )


def test_render_emits_min_and_max_height_bounds():
    html = render_text_layer(_two_block_model(), {"s1": "Một", "s2": "Hai"},
                             image_url_base="http://api/assets")
    # CSS contains one min-height rule; each block adds one inline min-height.
    # Count inline-style occurrences by checking the no-space variant used by _pct.
    # The CSS rule uses "min-height: 100%" (with space), so "min-height:5" or
    # "min-height:1" only comes from inline styles.
    # Use max-height which only appears in inline styles (not in _CSS constant).
    assert html.count("max-height:") == 2
    assert html.count("min-height:5.938%") == 2  # inline bound per block, CSS-independent


def test_render_max_height_uses_slot_not_bbox():
    # s1 slot = next-top(200) - top(100) = 100pt -> 100/842*100 = 11.876%,
    # larger than its bbox-height bound 50/842*100 = 5.938%.
    html = render_text_layer(_two_block_model(), {"s1": "Một", "s2": "Hai"},
                             image_url_base="http://api/assets")
    assert "max-height:11.876%" in html   # slot-based, not 5.938%
    assert "min-height:5.938%" in html     # bbox-height floor
