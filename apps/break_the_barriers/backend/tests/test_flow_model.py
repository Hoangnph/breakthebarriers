from backend.app.services.page_model import PageModel, Block, Figure, FontSpec
from backend.app.services.flow_model import build_document_flow, FlowElement


def _txt(span, role, top, size):
    return Block(span_id=span, role=role, bbox=[72, top, 300, 20], text="",
                 font=FontSpec(size, 700 if role == "heading" else 400, False, "#000", "left", "sans"))


def test_text_page_flows_blocks_in_top_order():
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[_txt("h", "heading", 40, 28), _txt("p1", "body", 80, 11),
                             _txt("c", "caption", 200, 9)],
                     figures=[Figure(bbox=[72, 120, 100, 50], img="f.png")],
                     page_class="text", cover="none")
    flow = build_document_flow([page])
    kinds = [(e.kind, e.span_id or e.src) for e in flow]
    assert kinds == [("heading", "h"), ("paragraph", "p1"),
                     ("figure", "f.png"), ("caption", "c")]
    assert flow[0].level == 1


def test_clean_photo_page_emits_image_block():
    page = PageModel(page_w=595.0, page_h=842.0, kind="mixed",
                     background={"color": "#000", "image": "p1.png", "clean_image": "p1.clean.png"},
                     blocks=[_txt("t", "heading", 500, 36)], figures=[],
                     page_class="regenerable", cover="front")
    flow = build_document_flow([page])
    assert flow[0].kind == "image_block"
    assert flow[0].src == "p1.clean.png"
    assert any(e.kind == "heading" and e.span_id == "t" for e in flow)


def test_base_color_page_has_no_image_block():
    page = PageModel(page_w=595.0, page_h=842.0, kind="mixed",
                     background={"color": "#000", "image": "p2.png"},
                     blocks=[_txt("b", "body", 40, 11)], figures=[],
                     page_class="regenerable", cover="none")
    flow = build_document_flow([page])
    assert all(e.kind != "image_block" for e in flow)


def test_heading_levels_ranked_by_font_size():
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[_txt("big", "heading", 40, 32), _txt("med", "heading", 80, 20),
                             _txt("body", "body", 120, 11)],
                     figures=[], page_class="text", cover="none")
    flow = {e.span_id: e for e in build_document_flow([page]) if e.span_id}
    assert flow["big"].level == 1 and flow["med"].level == 2
    assert flow["body"].kind == "paragraph"
