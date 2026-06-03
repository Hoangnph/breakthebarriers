from PIL import Image
from backend.app.services.page_image import is_photo_background
from backend.app.services.page_classifier import classify_kind


def test_white_page_is_not_photo(tmp_path):
    img = Image.new("RGB", (200, 280), (255, 255, 255))
    p = tmp_path / "white.png"
    img.save(p)
    # a small text box near the top; rest is white paper
    assert is_photo_background(str(p), 100, 140, [[10, 10, 60, 10]], [],
                               scale_x=2.0, scale_y=2.0) is False


def test_dark_gradient_page_is_photo(tmp_path):
    img = Image.new("RGB", (200, 280), (0, 0, 0))
    # vertical blue gradient => clearly not paper
    for y in range(280):
        for x in range(200):
            img.putpixel((x, y), (5, 10, int(40 + y * 0.6)))
    p = tmp_path / "cover.png"
    img.save(p)
    # text occupies a small region; the rest is the photo background
    assert is_photo_background(str(p), 100, 140, [[10, 100, 80, 20]], [],
                               scale_x=2.0, scale_y=2.0) is True


def test_missing_file_defaults_false(tmp_path):
    assert is_photo_background(str(tmp_path / "nope.png"), 100, 140, [], [],
                              scale_x=1.0, scale_y=1.0) is False


def test_classify_photo_bg_with_text_is_mixed():
    # photo background + meaningful text => keep raster, overlay text
    # Two blocks of 200x80 = 32000 px total on a 595x842 page (~6.4%) — above text_min_ratio (0.06)
    blocks = [[40, 600, 200, 80], [40, 700, 200, 80]]
    assert classify_kind(595, 842, blocks, [], bg_is_photo=True) == "mixed"


def test_classify_photo_bg_no_text_is_image():
    assert classify_kind(595, 842, [], [], bg_is_photo=True) == "image"


def test_classify_default_unchanged_without_photo_flag():
    # regression: existing behavior when bg_is_photo not passed
    blocks = [[0, i * 20, 400, 15] for i in range(20)]
    assert classify_kind(595, 842, blocks, []) == "text"
