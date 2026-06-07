from backend.app.services.page_model import PageModel, Block, Figure, FontSpec
from backend.app.services.flow_model import (
    build_document_flow, FlowElement, flow_span_id, running_header_spans,
)


def _txt(span, role, top, size):
    return Block(span_id=span, role=role, bbox=[72, top, 300, 20], text="",
                 font=FontSpec(size, 700 if role == "heading" else 400, False, "#000", "left", "sans"))


def test_text_page_flows_blocks_in_top_order():
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[_txt("h", "heading", 40, 28), _txt("p1", "body", 80, 11),
                             _txt("c", "caption", 200, 9)],
                     figures=[Figure(bbox=[72, 120, 100, 50], img="f.png")],
                     page_class="text", cover="none", page_num=1)
    flow = build_document_flow([page])
    kinds = [(e.kind, e.span_id or e.src) for e in flow]
    assert kinds == [("heading", "p1-h"), ("paragraph", "p1-p1"),
                     ("figure", "f.png"), ("caption", "p1-c")]
    assert flow[0].level == 1


def test_design_page_emits_image_block_only_no_text():
    # Design/cover page: keep the full-page image, do NOT re-flow its text.
    # Prefer the original raster (with title) over the text-removed clean_image.
    page = PageModel(page_w=595.0, page_h=842.0, kind="mixed",
                     background={"color": "#000", "image": "p1.png", "clean_image": "p1.clean.png"},
                     blocks=[_txt("t", "heading", 500, 36)], figures=[],
                     page_class="regenerable", cover="front", page_num=1)
    flow = build_document_flow([page])
    assert [e.kind for e in flow] == ["image_block"]
    assert flow[0].src == "p1.png"
    assert all(e.span_id != "p1-t" for e in flow)


def test_text_heavy_keep_raster_page_flows_html_not_image():
    # keep-raster from an uncertain `preserve` class but text-heavy (>4 blocks):
    # must flow HTML so content stays readable — NOT collapse to a full-page image.
    blocks = [_txt(f"b{i}", "body", 40 + i * 20, 11) for i in range(6)]
    page = PageModel(page_w=595.0, page_h=842.0, kind="mixed",
                     background={"color": "#000", "image": "p4.png"},
                     blocks=blocks, figures=[],
                     page_class="preserve", cover="none", page_num=4)
    flow = build_document_flow([page])
    assert all(e.kind != "image_block" for e in flow)
    assert any(e.span_id == "p4-b0" for e in flow)


def test_sparse_keep_raster_page_becomes_image():
    # keep-raster, non-cover, few text blocks (<=4): stays a full-page image.
    page = PageModel(page_w=595.0, page_h=842.0, kind="mixed",
                     background={"color": "#000", "image": "p30.png"},
                     blocks=[_txt("x", "body", 40, 11)], figures=[],
                     page_class="preserve", cover="none", page_num=30)
    flow = build_document_flow([page])
    assert [e.kind for e in flow] == ["image_block"]
    assert flow[0].src == "p30.png"


def test_base_color_page_has_no_image_block():
    page = PageModel(page_w=595.0, page_h=842.0, kind="mixed",
                     background={"color": "#000", "image": "p2.png"},
                     blocks=[_txt("b", "body", 40, 11)], figures=[],
                     page_class="regenerable", cover="none", page_num=1)
    flow = build_document_flow([page])
    assert all(e.kind != "image_block" for e in flow)


def test_heading_levels_ranked_by_font_size():
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[_txt("big", "heading", 40, 32), _txt("med", "heading", 80, 20),
                             _txt("body", "body", 120, 11)],
                     figures=[], page_class="text", cover="none", page_num=1)
    flow = {e.span_id: e for e in build_document_flow([page]) if e.span_id}
    assert flow["p1-big"].level == 1 and flow["p1-med"].level == 2
    assert flow["p1-body"].kind == "paragraph"


def test_span_ids_are_globally_unique_across_pages():
    # Same page-local span_id "s1" on two different pages must NOT collide.
    def mk(num):
        return PageModel(page_w=595.0, page_h=842.0, kind="text",
                         background={"color": "#fff", "image": None},
                         blocks=[_txt("s1", "heading", 40, 28)], figures=[],
                         page_class="text", cover="none", page_num=num)
    flow = build_document_flow([mk(3), mk(7)])
    ids = [e.span_id for e in flow if e.span_id]
    assert ids == ["p3-s1", "p7-s1"]
    assert len(set(ids)) == len(ids)   # no duplicate anchors


def test_running_header_spans_flags_repeated_short_line():
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
    entries = []
    for pn in range(1, 9):
        entries.append((pn, "s1", "INTRODUCTION TO AI"))            # running header
        entries.append((pn, "s2", f"{words[pn - 1]} body paragraph unique here."))
    spans = running_header_spans(entries)
    assert flow_span_id(1, "s1") in spans and flow_span_id(8, "s1") in spans
    assert flow_span_id(1, "s2") not in spans     # unique content kept


def test_running_header_spans_normalizes_footer_page_numbers():
    # Footer text differs only by page number; digit-stripped normalization matches.
    entries = [(pn, "f", f"World Travel Council  {pn}") for pn in range(1, 9)]
    spans = running_header_spans(entries)
    assert flow_span_id(5, "f") in spans


def test_running_header_spans_noop_small_doc():
    entries = [(1, "a", "Header"), (2, "a", "Header"), (3, "a", "Header")]
    assert running_header_spans(entries) == set()   # < 4 pages → no-op


def test_title_inside_cleaned_figure_becomes_overlay_banner():
    # A heading inside a TEXT-CLEANED banner figure becomes an overlay on that
    # figure (rendered from clean_img): the figure is not emitted separately, the
    # heading keeps its span (so it still appears in the contents nav).
    banner = Figure(bbox=[0, 0, 595, 192], img="banner.png", clean_img="banner.clean.png")
    title = Block(span_id="t", role="heading", bbox=[36, 146, 182, 43], text="",
                  font=FontSpec(36, 700, False, "#ffffff", "left", "sans"))
    body = _txt("b", "body", 230, 11)
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[title, body], figures=[banner],
                     page_class="text", cover="none", page_num=3)
    flow = build_document_flow([page])
    assert all(e.kind != "figure" for e in flow)            # banner consumed
    h = next(e for e in flow if e.kind == "heading")
    assert h.span_id == "p3-t" and h.overlay is not None
    assert h.overlay["src"] == "banner.clean.png"           # cleaned background used
    assert h.overlay["color"] == "#ffffff" and h.overlay["weight"] == 700
    assert 0 <= h.overlay["left"] < 20 and 60 < h.overlay["top"] < 90   # bottom-left


def test_uncleaned_banner_is_not_overlaid():
    # No clean_img → overlaying would double the baked-in text, so DON'T bond:
    # the figure stays standalone and the title flows normally (no overlay).
    banner = Figure(bbox=[0, 0, 595, 192], img="banner.png")   # no clean_img
    title = Block(span_id="t", role="heading", bbox=[36, 146, 182, 43], text="",
                  font=FontSpec(36, 700, False, "#ffffff", "left", "sans"))
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[title], figures=[banner],
                     page_class="text", cover="none", page_num=3)
    flow = build_document_flow([page])
    assert any(e.kind == "figure" and e.src == "banner.png" for e in flow)
    h = next(e for e in flow if e.kind == "heading")
    assert h.overlay is None


def test_figure_overlapping_many_blocks_is_not_a_banner():
    # A figure overlapping many text blocks is a content region, not a banner —
    # even if cleaned, it must not become an overlay.
    big = Figure(bbox=[0, 0, 595, 800], img="big.png", clean_img="big.clean.png")
    blocks = [Block(span_id=f"s{i}", role="body", bbox=[60, 40 + i * 40, 400, 20],
                    text="", font=FontSpec(11, 400, False, "#000", "left", "sans"))
              for i in range(6)]
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=blocks, figures=[big],
                     page_class="text", cover="none", page_num=27)
    flow = build_document_flow([page])
    assert all(e.overlay is None for e in flow)
    assert any(e.kind == "figure" for e in flow)


def test_narrow_figure_with_label_is_not_a_banner():
    # A narrow example image / icon with a small label must NOT become a banner,
    # even if cleaned — it stays a standalone figure showing its ORIGINAL image.
    icon = Figure(bbox=[40, 100, 120, 120], img="icon.png", clean_img="icon.clean.png")  # ~20% wide
    label = Block(span_id="t", role="heading", bbox=[60, 150, 40, 20], text="",
                  font=FontSpec(18, 700, False, "#fff", "left", "sans"))
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[label], figures=[icon],
                     page_class="text", cover="none", page_num=26)
    flow = build_document_flow([page])
    assert all(e.overlay is None for e in flow)
    assert any(e.kind == "figure" and e.src == "icon.png" for e in flow)   # original, not clean


def test_block_outside_figure_keeps_separate_figure_with_original_image():
    # Standalone figures always render the ORIGINAL image, never the cleaned one.
    fig = Figure(bbox=[72, 120, 100, 50], img="f.png", clean_img="f.clean.png")
    page = PageModel(page_w=595.0, page_h=842.0, kind="text",
                     background={"color": "#fff", "image": None},
                     blocks=[_txt("h", "heading", 40, 28)], figures=[fig],
                     page_class="text", cover="none", page_num=1)
    flow = build_document_flow([page])
    assert any(e.kind == "figure" and e.src == "f.png" for e in flow)   # original image
    h = next(e for e in flow if e.kind == "heading")
    assert h.overlay is None
