from backend.app.services.page_eligibility import classify_page, detect_cover


# --- classify_page ---
def test_table_forces_preserve():
    assert classify_page(0.4, 0.2, ["photo"], has_table=True, bg_is_photo=False) == "preserve"


def test_diagram_figure_forces_preserve():
    assert classify_page(0.1, 0.5, ["diagram"], has_table=False, bg_is_photo=False) == "preserve"


def test_uncertain_figure_forces_preserve():
    assert classify_page(0.1, 0.5, ["uncertain"], has_table=False, bg_is_photo=False) == "preserve"


def test_all_photo_low_text_is_regenerable():
    assert classify_page(0.1, 0.5, ["photo", "photo"], has_table=False, bg_is_photo=False) == "regenerable"


def test_photo_background_cover_is_regenerable():
    assert classify_page(0.24, 0.03, [], has_table=False, bg_is_photo=True) == "regenerable"


def test_no_image_with_text_is_text():
    assert classify_page(0.4, 0.0, [], has_table=False, bg_is_photo=False) == "text"


def test_text_heavy_page_with_photo_is_preserve():
    assert classify_page(0.5, 0.2, ["photo"], has_table=False, bg_is_photo=False) == "preserve"


# --- detect_cover ---
def test_front_cover_first_page_image_low_text():
    assert detect_cover(0, 44, text_ratio=0.24, fig_ratio=0.03, bg_is_photo=True) == "front"


def test_back_cover_last_page_image_dominant():
    assert detect_cover(43, 44, text_ratio=0.07, fig_ratio=0.80, bg_is_photo=False) == "back"


def test_middle_page_is_not_cover():
    assert detect_cover(5, 44, text_ratio=0.30, fig_ratio=0.20, bg_is_photo=False) == "none"


def test_text_heavy_first_page_is_not_cover():
    assert detect_cover(0, 44, text_ratio=0.50, fig_ratio=0.02, bg_is_photo=False) == "none"
