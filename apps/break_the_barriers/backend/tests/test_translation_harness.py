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


def test_judge_single_and_empty_candidates():
    blocks = [{"text": "Hello", "span_ids": ["s1"]}]
    assert H._judge(blocks, [], "vi", {})[0]["score"] == 0           # 0 ứng viên
    one = H._judge(blocks, [["Xin chào"]], "vi", {})                  # 1 ứng viên → idx 0
    assert one[0]["best_idx"] == 0 and one[0]["score"] >= 0


def test_judge_uses_parsed_result(monkeypatch):
    blocks = [{"text": "Hello", "span_ids": ["s1"]},
              {"text": "World", "span_ids": ["s2"]}]
    cands = [["A0", "B0"], ["A1", "B1"]]
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(H, "_judge_call",
                        staticmethod(lambda items: [
                            {"id": "b0", "best_idx": 1, "score": 92, "critique": "good"},
                            {"id": "b1", "best_idx": 0, "score": 60, "critique": "weak"}]))
    out = H._judge(blocks, cands, "vi", {})
    assert out[0]["best_idx"] == 1 and out[0]["score"] == 92
    assert out[1]["best_idx"] == 0 and out[1]["score"] == 60


def test_generate_candidates_aggregates(monkeypatch):
    blocks = [{"text": "Hello", "span_ids": ["s1"]}]
    calls = {"n": 0}

    def fake_variant(blocks, tl, ctx, gl, model, temp, style):
        calls["n"] += 1
        return [f"{style}-{model}"]
    monkeypatch.setattr(H, "_batch_translate_variant", staticmethod(fake_variant))
    cands = H._generate_candidates(blocks, "vi", {}, [])
    assert calls["n"] == 3 and len(cands) == 3       # 3 biến thể
    assert all(len(c) == 1 for c in cands)


def test_generate_candidates_skips_failed_variant(monkeypatch):
    blocks = [{"text": "Hello", "span_ids": ["s1"]}]
    seq = [None, ["ok"], None]
    monkeypatch.setattr(H, "_batch_translate_variant",
                        staticmethod(lambda *a, **k: seq.pop(0)))
    cands = H._generate_candidates(blocks, "vi", {}, [])
    assert len(cands) == 1                            # bỏ 2 cái None


def test_refine_maps_improved_back(monkeypatch):
    items = [{"block_index": 2, "source": "Hi", "current": "x", "critique": "weak"}]
    monkeypatch.setattr(H, "_refine_call",
                        staticmethod(lambda payload: {"r0": "Xin chào"}))
    out = H._refine(items, "vi", {}, [])
    assert out == {2: "Xin chào"}


def test_refine_empty_returns_empty():
    assert H._refine([], "vi", {}, []) == {}
