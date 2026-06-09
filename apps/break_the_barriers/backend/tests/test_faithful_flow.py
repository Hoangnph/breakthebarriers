from backend.app.services.page_model import PageModel, Block, FontSpec
from backend.app.services.faithful_flow_renderer import (
    render_faithful_page, render_faithful_flow)


def _text_page(page_num):
    blk = Block(span_id="s1", role="body", bbox=[72, 100, 300, 40], text="",
                font=FontSpec(11, 400, False, "#000000", "left", "sans"),
                box={"mode": "scrim", "fill": "rgba(255,255,255,0.55)"})
    return PageModel(595.0, 842.0, "text", {"color": "#fff", "image": None}, [blk], [],
                     page_class="text", cover="none", page_num=page_num)


def test_fragment_has_aspect_and_raster_fallback():
    html = render_faithful_page(_text_page(38), {"s1": "đoạn dịch"}, "http://x/assets")
    assert 'class="ff-page"' in html
    assert "aspect-ratio:595.00/842.00" in html
    assert '<img class="ff-bg" src="http://x/assets/page-38.png"' in html


def test_fragment_overlay_text_in_cqw_with_mask():
    html = render_faithful_page(_text_page(38), {"s1": "đoạn dịch"}, "http://x/assets")
    assert "đoạn dịch" in html
    assert "cqw" in html and "data-cqw=" in html
    assert "background:rgba(255,255,255,0.9)" in html


def test_fragment_skips_blocks_without_translation_but_keeps_raster():
    html = render_faithful_page(_text_page(1), {}, "http://x/assets")
    assert 'class="ff-text"' not in html
    assert '<img class="ff-bg"' in html


def test_flow_stacks_pages_in_order_with_scripts():
    html = render_faithful_flow([_text_page(2), _text_page(1)],
                                {1: {"s1": "một"}, 2: {"s1": "hai"}}, "http://x/assets")
    assert html.count('class="ff-page"') == 2
    assert html.index('id="pg-1"') < html.index('id="pg-2"')
    assert "btb-zoom" in html and "data-cqw" in html
    assert "một" in html and "hai" in html


def test_flow_empty_pages_valid_shell():
    html = render_faithful_flow([], {}, "http://x/a")
    assert '<article class="ff-doc">' in html
    assert html.count('class="ff-page"') == 0


def test_flow_endpoint_overlays_translation(client, db_session):
    import json
    from backend.app.models_db import DBDocument, DBPage, DBTranslation
    db_session.add(DBDocument(id="ffdoc", filename="f.pdf", total_pages=2, status="translated"))
    m = {"page_w": 595.0, "page_h": 842.0, "kind": "text",
         "background": {"color": "#fff", "image": None},
         "blocks": [{"span_id": "s1", "role": "body", "bbox": [72, 100, 300, 40], "text": "",
                     "font": {"size": 11, "weight": 400, "italic": False, "color": "#000000",
                              "align": "left", "family_class": "sans"},
                     "box": {"mode": "scrim", "fill": "rgba(255,255,255,0.55)"}}],
         "figures": [], "page_class": "text", "cover": "none"}
    for n in (1, 2):
        db_session.add(DBPage(document_id="ffdoc", page_num=n, original_html="<p/>",
                              status="translated", model_json=json.dumps(m)))
    db_session.add(DBTranslation(document_id="ffdoc", page_num=1, span_id="s1",
                                 original_text="a", translated_text="dịch một"))
    db_session.commit()
    r = client.get("/api/docs/ffdoc/flow?lang=vi")
    assert r.status_code == 200
    assert r.text.count('class="ff-page"') == 2
    assert "page-1.png" in r.text and "page-2.png" in r.text
    assert "dịch một" in r.text


def test_flow_endpoint_unknown_doc_404(client):
    assert client.get("/api/docs/nope-doc/flow").status_code == 404
