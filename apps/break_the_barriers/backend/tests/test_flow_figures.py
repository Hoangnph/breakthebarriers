from backend.app.services.page_model import PageModel, Figure
from backend.app.services.flow_model import FlowElement, build_document_flow
from backend.app.services.flow_renderer import render_flow_html


def _page(figs, blocks=None):
    return PageModel(page_w=595, page_h=842, kind="mixed",
                     background={"color": "#fff", "image": None},
                     blocks=blocks or [], figures=figs,
                     page_class="text", cover="none", page_num=1)


def test_flow_passes_figure_align():
    pm = _page([Figure(bbox=[158, 53, 282, 273], img="f.png", align="center")])
    flow = build_document_flow([pm])
    figs = [e for e in flow if e.kind == "figure"]
    assert figs and figs[0].align == "center"


def test_flow_does_not_drop_figures():
    pm = _page([Figure(bbox=[60, 60, 120, 120], img="a.png"),
                Figure(bbox=[300, 60, 120, 120], img="b.png")])
    flow = build_document_flow([pm])
    srcs = {e.src for e in flow if e.kind == "figure"}
    assert srcs == {"a.png", "b.png"}


def test_renderer_centers_figure():
    html = render_flow_html(
        [FlowElement(kind="figure", src="f.png", align="center")], {}, "http://x/assets")
    assert "text-align:center" in html
    assert "http://x/assets/f.png" in html


def test_renderer_sanitizes_bad_align():
    html = render_flow_html(
        [FlowElement(kind="figure", src="f.png", align="evil;}")], {}, "http://x/assets")
    assert "evil" not in html
    assert "text-align:left" in html
