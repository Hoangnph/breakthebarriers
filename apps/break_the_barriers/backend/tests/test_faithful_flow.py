from backend.app.services.faithful_flow_renderer import render_faithful_flow


def test_one_img_per_page_in_sorted_order():
    html = render_faithful_flow([3, 1, 2], "http://api/assets")
    assert html.count('class="fr-img"') == 3
    assert html.index("page-1.png") < html.index("page-2.png") < html.index("page-3.png")
    for n in (1, 2, 3):
        assert f'src="http://api/assets/page-{n}.png"' in html
        assert f'id="pg-{n}"' in html


def test_empty_pages_returns_valid_shell():
    html = render_faithful_flow([], "http://api/a")
    assert '<article class="fr-doc">' in html
    assert html.count('class="fr-img"') == 0


def test_has_zoom_script():
    assert "btb-zoom" in render_faithful_flow([1], "http://api/a")


def test_escapes_base_url():
    html = render_faithful_flow([1], 'http://a/x"onerror')
    assert 'x"onerror' not in html
    assert "&quot;" in html
