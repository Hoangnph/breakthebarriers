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


def _raster_model(page_class, cover):
    return PageModel(
        page_w=595.0, page_h=842.0, kind="mixed",
        background={"color": "#3c84bf", "image": "page-2.png"},
        blocks=[Block(span_id="s1", role="body", bbox=[70, 480, 300, 14],
                      text="", font=FontSpec(11, 400, False, "#000", "left", "sans"),
                      box={"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})],
        figures=[],
        page_class=page_class, cover=cover,
    )


def test_base_color_page_omits_raster_and_box():
    html = render_text_layer(_raster_model("regenerable", "none"),
                             {"s1": "Mục lục"}, image_url_base="http://api/assets")
    assert 'class="tl-bg"' not in html
    assert "page-2.png" not in html
    assert "rgba(255,255,255,0.55)" not in html
    assert "Mục lục" in html


def test_preserve_page_keeps_raster_and_box():
    html = render_text_layer(_raster_model("preserve", "none"),
                             {"s1": "X"}, image_url_base="http://api/assets")
    assert 'class="tl-bg"' in html
    assert "page-2.png" in html
    assert "rgba(255,255,255,0.55)" in html


def test_front_cover_keeps_raster_phase1():
    html = render_text_layer(_raster_model("regenerable", "front"),
                             {"s1": "X"}, image_url_base="http://api/assets")
    assert 'class="tl-bg"' in html


def _clean_photo_model(clean_image=None):
    bg = {"color": "#000", "image": "page-1.png"}
    if clean_image:
        bg["clean_image"] = clean_image
    return PageModel(
        page_w=595.0, page_h=842.0, kind="mixed", background=bg,
        blocks=[Block(span_id="s1", role="heading", bbox=[36, 516, 432, 60],
                      text="", font=FontSpec(36, 700, False, "#fff", "left", "sans"))],
        figures=[],
        page_class="regenerable", cover="front",
    )


def test_clean_photo_uses_clean_image_when_present():
    html = render_text_layer(_clean_photo_model("page-1.clean.png"),
                             {"s1": "X"}, image_url_base="http://api/assets")
    assert "page-1.clean.png" in html
    # original raster must NOT be referenced (strip the clean name first to avoid substring match)
    assert "page-1.png" not in html.replace("page-1.clean.png", "")


def test_clean_photo_falls_back_to_raster_when_not_cleaned():
    html = render_text_layer(_clean_photo_model(None),
                             {"s1": "X"}, image_url_base="http://api/assets")
    assert "page-1.png" in html


def test_clean_photo_text_background_is_transparent():
    # On a clean-photo page the background is already AI-cleaned, so the overlay
    # text must NOT carry a scrim/fill box — it sits directly on the clean photo.
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="mixed",
        background={"color": "#000", "image": "page-1.png",
                    "clean_image": "page-1.clean-inpaint.png"},
        blocks=[Block(span_id="s1", role="heading", bbox=[36, 516, 432, 60], text="",
                      font=FontSpec(36, 700, False, "#fff", "left", "sans"),
                      box={"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})],
        figures=[], page_class="regenerable", cover="front")
    html = render_text_layer(pm, {"s1": "X"}, image_url_base="http://api/assets")
    assert "rgba(255,255,255,0.55)" not in html


def test_policy_override_forces_base_color_on_preserve():
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="mixed",
        background={"color": "#000", "image": "page-1.png", "policy_override": "base-color"},
        blocks=[Block(span_id="s1", role="body", bbox=[70, 480, 300, 14], text="",
                      font=FontSpec(11, 400, False, "#000", "left", "sans"))],
        figures=[], page_class="preserve", cover="none")
    html = render_text_layer(pm, {"s1": "X"}, image_url_base="http://api/assets")
    assert 'class="tl-bg"' not in html          # override base-color drops raster


def test_blocks_carry_data_span_and_edit_script():
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#fff", "image": None},
        blocks=[Block(span_id="s1", role="body", bbox=[72, 40, 200, 24], text="",
                      font=FontSpec(11, 400, False, "#000", "left", "sans"))],
        figures=[], page_class="text", cover="none")
    html = render_text_layer(pm, {"s1": "Xin chào"}, image_url_base="http://api/assets")
    assert 'data-span="s1"' in html
    assert "btb-edit" in html


def test_base_color_renders_on_white_not_sampled_color():
    # A base-color content page must use a WHITE page background, not the dark
    # sampled photo color (e.g. #3c84bf) left over from the original raster.
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="mixed",
        background={"color": "#3c84bf", "image": "page-2.png"},
        blocks=[], figures=[], page_class="regenerable", cover="none")
    html = render_text_layer(pm, {}, image_url_base="http://api/assets")
    assert "background:#ffffff" in html
    assert "#3c84bf" not in html


def test_figure_uses_clean_img_when_present():
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#fff", "image": None},
        blocks=[],
        figures=[Figure(bbox=[10, 10, 100, 50], img="f1.png", clean_img="f1.clean.png")],
        page_class="text", cover="none")
    html = render_text_layer(pm, {}, image_url_base="http://api/assets")
    assert "f1.clean.png" in html
    assert "f1.png" not in html.replace("f1.clean.png", "")


def test_figure_falls_back_to_img_without_clean():
    pm = PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#fff", "image": None},
        blocks=[], figures=[Figure(bbox=[10, 10, 100, 50], img="f1.png")],
        page_class="text", cover="none")
    html = render_text_layer(pm, {}, image_url_base="http://api/assets")
    assert "f1.png" in html
