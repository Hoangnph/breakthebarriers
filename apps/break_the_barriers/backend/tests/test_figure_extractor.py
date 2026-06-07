from PIL import Image
from backend.app.services.figure_extractor import crop_figure


def test_crop_figure_writes_scaled_region(tmp_path):
    img = Image.new("RGB", (200, 100), (255, 255, 255))
    for x in range(20, 60):
        for y in range(20, 60):
            img.putpixel((x, y), (255, 0, 0))
    # bbox in points: l=10,t=10,w=20,h=20 -> px (20,20,40,40) at scale 2
    fname = crop_figure(img, [10, 10, 20, 20], scale_x=2.0, scale_y=2.0,
                        output_dir=str(tmp_path), doc_id="d", page_no=1, idx=1)
    assert fname == "d-1-fig1.png"
    out = Image.open(tmp_path / "d-1-fig1.png")
    assert out.size == (40, 40)
    assert out.getpixel((0, 0)) == (255, 0, 0)


def test_crop_figure_clamps_to_bounds(tmp_path):
    img = Image.new("RGB", (50, 50), (0, 0, 0))
    fname = crop_figure(img, [40, 40, 100, 100], scale_x=1.0, scale_y=1.0,
                        output_dir=str(tmp_path), doc_id="d", page_no=2, idx=3)
    assert (tmp_path / fname).exists()
    assert Image.open(tmp_path / fname).size == (10, 10)


def test_figure_has_overlaid_title_detects_banner():
    from backend.app.services.extractor import _figure_has_overlaid_title
    fb = [0, 0, 595, 192]                       # full-width banner
    blocks = [{"bbox": [36, 146, 182, 43]}]     # title sitting on the banner
    assert _figure_has_overlaid_title(blocks, fb) is True


def test_figure_has_overlaid_title_ignores_block_outside():
    from backend.app.services.extractor import _figure_has_overlaid_title
    fb = [0, 0, 595, 192]
    blocks = [{"bbox": [60, 400, 400, 20]}]     # body text well below the figure
    assert _figure_has_overlaid_title(blocks, fb) is False


def test_figure_has_overlaid_title_rejects_content_region():
    from backend.app.services.extractor import _figure_has_overlaid_title
    fb = [0, 0, 595, 800]                       # large region overlapping many blocks
    blocks = [{"bbox": [60, 40 + i * 40, 400, 20]} for i in range(8)]
    assert _figure_has_overlaid_title(blocks, fb) is False
