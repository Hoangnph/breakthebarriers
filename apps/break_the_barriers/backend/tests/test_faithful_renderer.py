from backend.app.services.faithful_renderer import render_faithful_page

LAYER = {"page_w": 400, "page_h": 300,
         "spans": [{"bbox": [50, 60, 120, 24], "text": "Hello <World>"}]}


def test_render_svg_inlines_and_overlays_transparent_text():
    html = render_faithful_page("<svg id='x'></svg>", "svg", LAYER, 400, 300)
    assert "<svg id='x'></svg>" in html          # SVG inline nguyên văn
    assert 'class="ff-tl"' in html               # lớp text vô hình
    assert "left:50.00px" in html and "top:60.00px" in html
    assert "Hello &lt;World&gt;" in html         # text được escape
    assert "width:400" in html and "height:300"  # container kích thước trang


def test_render_image_kind_uses_img_tag():
    html = render_faithful_page("docY-1.jpg", "image", LAYER, 400, 300,
                                asset_base="http://api/x/assets")
    assert '<img src="http://api/x/assets/docY-1.jpg"' in html
    assert "<svg" not in html
