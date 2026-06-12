from backend.app.services.translation_harness import TranslationHarness as H


def test_rule_check_empty_and_untranslated():
    assert H._rule_check("Hello world", "", [], "vi")[0] is False           # rỗng
    assert H._rule_check("Hello world", "Hello world", [], "vi")[0] is False  # chưa dịch
    assert H._rule_check("Hello world", "Xin chào thế giới", [], "vi")[0] is True


def test_rule_check_length_glossary_format():
    assert H._rule_check("Hi", "a" * 50, [], "vi")[0] is False               # quá dài >3x
    gl = [{"source": "AI", "target": "Trí tuệ nhân tạo"}]
    assert H._rule_check("AI is here", "Nó ở đây", gl, "vi")[0] is False      # thiếu glossary
    assert H._rule_check("AI is here", "Trí tuệ nhân tạo ở đây", gl, "vi")[0] is True
    assert H._rule_check("Pay 50%", "Tra tien", [], "vi")[0] is False         # mất format số
    assert H._rule_check("Pay 50%", "Trả 50%", [], "vi")[0] is True


def test_parse_judge_json_handles_fences():
    raw = '```json\n[{"id":"b0","best_idx":1,"score":90,"critique":"ok"}]\n```'
    parsed = H._parse_judge_json(raw)
    assert parsed and parsed[0]["best_idx"] == 1
    assert H._parse_judge_json("not json") is None
