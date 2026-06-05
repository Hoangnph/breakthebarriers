import json
from backend.app.services.page_model import FontSpec, Block, Figure, PageModel


def test_pagemodel_roundtrip_with_font():
    m = PageModel(
        page_w=595.0, page_h=842.0, kind="text",
        background={"color": "#ffffff", "image": None},
        blocks=[Block(
            span_id="s1", role="heading", bbox=[72.0, 40.0, 200.0, 24.0],
            text="Hello",
            font=FontSpec(size=24.0, weight=700, italic=False,
                          color="#1a1a1a", align="left", family_class="sans"),
        )],
        figures=[Figure(bbox=[0.0, 0.0, 595.0, 300.0], img="d-1-fig1.png")],
    )
    restored = PageModel.from_json(m.to_json())
    assert restored.kind == "text"
    assert restored.blocks[0].font.weight == 700
    assert restored.blocks[0].font.family_class == "sans"
    assert restored.figures[0].img == "d-1-fig1.png"
    assert json.loads(m.to_json())["page_w"] == 595.0


def test_pagemodel_roundtrip_font_none():
    m = PageModel(page_w=1.0, page_h=1.0, kind="image",
                  background={"color": "#000000", "image": "page-1.png"},
                  blocks=[Block(span_id="s2", role="body", bbox=[0, 0, 1, 1],
                                text="x", font=None)],
                  figures=[])
    restored = PageModel.from_json(m.to_json())
    assert restored.blocks[0].font is None
    assert restored.background["image"] == "page-1.png"


def test_pagemodel_defaults_page_class_and_cover():
    from backend.app.services.page_model import PageModel
    pm = PageModel(page_w=595.0, page_h=842.0, kind="text",
                   background={"color": "#fff", "image": None}, blocks=[], figures=[])
    assert pm.page_class == "text"
    assert pm.cover == "none"


def test_pagemodel_roundtrip_preserves_page_class_and_cover():
    from backend.app.services.page_model import PageModel
    pm = PageModel(page_w=1.0, page_h=1.0, kind="image",
                   background={"color": "#fff", "image": "p.png"}, blocks=[], figures=[],
                   page_class="regenerable", cover="front")
    d = pm.to_dict()
    assert d["page_class"] == "regenerable" and d["cover"] == "front"
    pm2 = PageModel.from_dict(d)
    assert pm2.page_class == "regenerable" and pm2.cover == "front"


def test_pagemodel_from_dict_old_json_defaults():
    from backend.app.services.page_model import PageModel
    pm = PageModel.from_dict({"page_w": 1.0, "page_h": 1.0, "kind": "text",
                              "background": {"color": "#fff", "image": None},
                              "blocks": [], "figures": []})
    assert pm.page_class == "text" and pm.cover == "none"


def test_figure_clean_img_roundtrip_and_default():
    from backend.app.services.page_model import PageModel, Figure
    pm = PageModel(page_w=1.0, page_h=1.0, kind="mixed",
                   background={"color": "#fff", "image": "p.png"}, blocks=[],
                   figures=[Figure(bbox=[0, 0, 10, 10], img="f.png", clean_img="f.clean.png")])
    d = pm.to_dict()
    assert d["figures"][0]["clean_img"] == "f.clean.png"
    pm2 = PageModel.from_dict(d)
    assert pm2.figures[0].clean_img == "f.clean.png"
    pm3 = PageModel.from_dict({"page_w": 1.0, "page_h": 1.0, "kind": "mixed",
                               "background": {"color": "#fff", "image": None},
                               "blocks": [], "figures": [{"bbox": [0, 0, 5, 5], "img": "g.png"}]})
    assert pm3.figures[0].clean_img is None
