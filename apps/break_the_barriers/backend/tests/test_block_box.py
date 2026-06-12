from backend.app.services.page_model import Block, FontSpec, PageModel


def test_block_box_roundtrip():
    b = Block(span_id="s1", role="heading", bbox=[0, 0, 10, 10], text="x",
              font=FontSpec(11, 400, False, "#111", "left", "sans"),
              box={"mode": "scrim", "fill": "rgba(0,0,0,0.45)"})
    m = PageModel(1, 1, "mixed", {"color": "#fff", "image": "p.png"}, [b], [])
    r = PageModel.from_json(m.to_json())
    assert r.blocks[0].box == {"mode": "scrim", "fill": "rgba(0,0,0,0.45)"}


def test_block_box_defaults_none():
    b = Block(span_id="s1", role="body", bbox=[0, 0, 1, 1], text="x", font=None)
    assert b.box is None
    m = PageModel.from_dict({"page_w": 1, "page_h": 1, "kind": "text",
                             "background": {"color": "#fff", "image": None},
                             "blocks": [{"span_id": "s1", "role": "body",
                                         "bbox": [0, 0, 1, 1], "text": "x", "font": None}],
                             "figures": []})
    assert m.blocks[0].box is None
