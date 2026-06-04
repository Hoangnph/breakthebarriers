from backend.app.services.background_policy import resolve_background_policy


def test_text_page_is_base_color():
    assert resolve_background_policy("text", "none") == "base-color"


def test_regenerable_content_page_is_base_color():
    assert resolve_background_policy("regenerable", "none") == "base-color"


def test_preserve_keeps_raster():
    assert resolve_background_policy("preserve", "none") == "keep-raster"


def test_front_cover_is_clean_photo():
    assert resolve_background_policy("regenerable", "front") == "clean-photo"


def test_back_cover_is_clean_photo():
    assert resolve_background_policy("regenerable", "back") == "clean-photo"


def test_unknown_defaults_to_keep_raster():
    assert resolve_background_policy("something-else", "none") == "keep-raster"
