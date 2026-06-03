from backend.app.services.semantic_tagger import label_to_role, tag_blocks


def test_label_to_role():
    assert label_to_role("section_header") == "heading"
    assert label_to_role("list_item") == "list"
    assert label_to_role("table") == "table"
    assert label_to_role("caption") == "caption"
    assert label_to_role("text") == "body"
    assert label_to_role(None) == "body"


def test_tag_blocks_assigns_role_from_overlap():
    blocks = [{"text": "T", "bbox": [10, 10, 100, 20]},
              {"text": "B", "bbox": [10, 200, 100, 20]}]
    docling_items = [
        {"label": "section_header", "bbox": [10, 10, 100, 20]},
        {"label": "picture", "bbox": [10, 500, 100, 20]},
    ]
    tagged = tag_blocks(blocks, docling_items)
    assert tagged[0]["role"] == "heading"
    assert tagged[1]["role"] == "body"


def test_tag_blocks_no_items_all_body():
    blocks = [{"text": "x", "bbox": [0, 0, 10, 10]}]
    assert tag_blocks(blocks, [])[0]["role"] == "body"
