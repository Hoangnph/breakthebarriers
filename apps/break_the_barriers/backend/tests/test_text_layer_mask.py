from backend.app.services.text_layer_renderer import _opaque_fill, _mask_css


def test_opaque_fill_raises_low_alpha():
    assert _opaque_fill("rgba(255,255,255,0.55)") == "rgba(255,255,255,0.9)"


def test_opaque_fill_keeps_high_alpha():
    assert _opaque_fill("rgba(0,0,0,0.95)") == "rgba(0,0,0,0.95)"


def test_opaque_fill_passes_hex_through():
    assert _opaque_fill("#010203") == "#010203"


def test_mask_css_scrim_has_padding():
    css = _mask_css({"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    assert "background:rgba(255,255,255,0.9)" in css
    assert "padding:0 2px" in css


def test_mask_css_fill_no_padding():
    assert _mask_css({"mode": "fill", "fill": "#010203"}) == "background:#010203;"


def test_mask_css_empty_without_fill():
    assert _mask_css(None) == ""
    assert _mask_css({"mode": "scrim"}) == ""


def test_text_page_always_draws_raster_and_masks():
    from backend.app.services.page_model import PageModel, Block, FontSpec
    from backend.app.services.text_layer_renderer import render_text_layer
    blk = Block(span_id="s1", role="body", bbox=[72, 100, 300, 40], text="",
                font=FontSpec(size=11, weight=400, italic=False, color="#000000",
                              align="left", family_class="sans"),
                box={"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    pm = PageModel(page_w=595, page_h=842, kind="text",
                   background={"color": "#ffffff", "image": None},
                   blocks=[blk], figures=[], page_class="text", cover="none", page_num=38)
    html = render_text_layer(pm, {"s1": "đoạn dịch"}, "http://x/assets")
    assert '<img class="tl-bg" src="http://x/assets/page-38.png"' in html
    assert "đoạn dịch" in html
    assert "background:rgba(255,255,255,0.9)" in html


def test_resolve_text_page_falls_back_to_page_raster():
    from backend.app.services.page_model import PageModel
    from backend.app.services.text_layer_renderer import resolve_page_raster
    pm = PageModel(595.0, 842.0, "text", {"color": "#fff", "image": None}, [], [],
                   page_class="text", cover="none", page_num=5)
    assert resolve_page_raster(pm) == ("page-5.png", True, False)


def test_resolve_override_base_color_drops_raster():
    from backend.app.services.page_model import PageModel
    from backend.app.services.text_layer_renderer import resolve_page_raster
    pm = PageModel(595.0, 842.0, "mixed",
                   {"color": "#000", "image": "page-1.png", "policy_override": "base-color"},
                   [], [], page_class="preserve", cover="none", page_num=1)
    assert resolve_page_raster(pm) == (None, False, True)


def test_resolve_clean_photo_uses_clean_image_no_mask():
    from backend.app.services.page_model import PageModel
    from backend.app.services.text_layer_renderer import resolve_page_raster
    pm = PageModel(595.0, 842.0, "mixed",
                   {"color": "#000", "image": "page-1.png", "clean_image": "page-1.clean.png"},
                   [], [], page_class="regenerable", cover="front", page_num=1)
    assert resolve_page_raster(pm) == ("page-1.clean.png", False, False)


def test_pages_endpoint_sets_page_num_for_raster(client, db_session):
    import json
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="tldoc", filename="f.pdf", total_pages=5, status="translated"))
    m = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
         "background": {"color": "#ffffff", "image": None},
         "blocks": [{"span_id": "s1", "role": "body", "bbox": [72, 100, 300, 40], "text": "",
                     "font": {"size": 11, "weight": 400, "italic": False, "color": "#000000",
                              "align": "left", "family_class": "sans"},
                     "box": {"mode": "scrim", "fill": "rgba(255,255,255,0.55)"}}],
         "figures": [], "page_class": "text", "cover": "none"}
    db_session.add(DBPage(document_id="tldoc", page_num=5, original_html="<p/>",
                          status="translated", model_json=json.dumps(m)))
    db_session.add(DBTranslation(document_id="tldoc", page_num=5, span_id="s1",
                                 original_text="x", translated_text="dịch"))
    db_session.commit()
    r = client.get("/api/docs/tldoc/pages/5?lang=vi&raw=true")
    assert r.status_code == 200
    assert "page-5.png" in r.text
