from PIL import Image
from backend.app.services.page_image import analyze_block_box


def test_uniform_region_returns_fill(tmp_path):
    img = Image.new("RGB", (200, 200), (250, 250, 250))
    p = tmp_path / "u.png"; img.save(p)
    box = analyze_block_box(str(p), [10, 10, 80, 40], 2.0, 2.0)
    assert box["mode"] == "fill"
    assert box["fill"].startswith("#")


def test_dark_photo_region_returns_dark_scrim(tmp_path):
    img = Image.new("RGB", (200, 200), (0, 0, 0))
    for y in range(200):
        for x in range(200):
            img.putpixel((x, y), (0, 0, min(255, y)))
    p = tmp_path / "d.png"; img.save(p)
    box = analyze_block_box(str(p), [0, 0, 100, 100], 2.0, 2.0)
    assert box["mode"] == "scrim"
    assert box["fill"] == "rgba(0,0,0,0.45)"


def test_light_photo_region_returns_light_scrim(tmp_path):
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    for y in range(200):
        for x in range(200):
            img.putpixel((x, y), (255, 255, max(0, 255 - y)))
    p = tmp_path / "l.png"; img.save(p)
    box = analyze_block_box(str(p), [0, 0, 100, 100], 2.0, 2.0)
    assert box["mode"] == "scrim"
    assert box["fill"] == "rgba(255,255,255,0.55)"


def test_missing_file_falls_back_to_fill(tmp_path):
    box = analyze_block_box(str(tmp_path / "nope.png"), [0, 0, 10, 10], 1.0, 1.0)
    assert box["mode"] == "fill"
    assert box["fill"].startswith("#")
