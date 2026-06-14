"""Tests cho chế độ dịch số lượng lớn qua Gemini Batch API (tier max).
Gemini-only, mock client (không gọi mạng)."""
from backend.app.services.translation_batch import BatchTranslator


# ── ETA / khuyến nghị cho khách hàng ──

def test_estimate_counts_candidate_requests_for_max_tier():
    """tier max = 3 ứng viên/trang → số request batch = pages × 3."""
    est = BatchTranslator.estimate(n_pages=100, quality="max")
    assert est["pages"] == 100
    assert est["candidate_requests"] == 300        # 100 × 3 variants


def test_estimate_presents_both_modes_with_wait_time():
    """Khách cần thấy RÕ thời gian chờ mỗi chế độ để chọn."""
    est = BatchTranslator.estimate(n_pages=340, quality="max")
    assert "online" in est and "batch" in est
    # online = ước tính theo phút (chạy tương tác)
    assert est["online"]["eta_seconds"] > 0
    assert "phút" in est["online"]["eta_text"] or "giờ" in est["online"]["eta_text"]
    # batch = bất đồng bộ, nêu rõ "tối đa 24h" + rẻ hơn
    assert "24" in est["batch"]["eta_text"]
    assert "50%" in est["batch"]["cost_note"]


def test_estimate_recommends_batch_for_large_docs():
    """Tài liệu lớn → khuyến nghị Batch (tiết kiệm + đỡ chờ tương tác)."""
    big = BatchTranslator.estimate(n_pages=340, quality="max")
    assert big["recommended_mode"] == "batch"
    assert big["recommendation"]                    # có câu khuyến nghị rõ ràng


def test_estimate_recommends_online_for_small_docs():
    """Tài liệu nhỏ → Nhanh (online) hợp lý hơn (xong trong phút)."""
    small = BatchTranslator.estimate(n_pages=5, quality="max")
    assert small["recommended_mode"] == "online"


# ── Dựng request batch (giữ NGUYÊN prompt harness max) ──

def test_build_candidate_requests_one_per_page_per_variant():
    pages = [
        [{"text": "Hello world"}, {"text": "Second block"}],   # trang 1: 2 block
        [{"text": "Page two"}],                                 # trang 2: 1 block
    ]
    reqs = BatchTranslator.build_candidate_requests(
        pages, "vi", {"domain": "general"}, [])
    # 2 trang × 3 variant = 6 request
    assert len(reqs) == 6
    keys = {r["key"] for r in reqs}
    assert "p0:v0" in keys and "p0:v2" in keys and "p1:v1" in keys
    r0 = next(r for r in reqs if r["key"] == "p0:v0")
    assert r0["model"] == "gemini-3.1-flash-lite"   # variant 0
    assert "Hello world" in r0["prompt"] and "Second block" in r0["prompt"]
    assert 0.0 <= r0["temperature"] <= 1.0


def test_parse_batch_results_maps_keys_to_block_translations():
    """Kết quả batch (key → JSON translations) → {key: [text theo block]}."""
    raw = [
        {"key": "p0:v0",
         "text": '{"translations":[{"id":"b0","text":"Xin chào"},{"id":"b1","text":"Khối hai"}]}'},
        {"key": "p1:v0", "text": '{"translations":[{"id":"b0","text":"Trang hai"}]}'},
    ]
    out = BatchTranslator.parse_batch_results(raw)
    assert out["p0:v0"] == ["Xin chào", "Khối hai"]
    assert out["p1:v0"] == ["Trang hai"]


def test_parse_batch_results_skips_malformed():
    raw = [{"key": "p0:v0", "text": "not json"},
           {"key": "p0:v1", "text": '{"translations":[{"id":"b0","text":"OK"}]}'}]
    out = BatchTranslator.parse_batch_results(raw)
    assert "p0:v0" not in out
    assert out["p0:v1"] == ["OK"]


# ── Submit / poll: bọc SDK, mock (không gọi mạng) ──

class _FakeBatches:
    def __init__(self):
        self.created = None

    def create(self, **kw):
        self.created = kw
        return type("J", (), {"name": "batches/abc123"})()

    def get(self, name):
        return type("J", (), {"name": name, "state": "JOB_STATE_RUNNING"})()


class _FakeClient:
    def __init__(self):
        self.batches = _FakeBatches()


def test_submit_returns_job_name_and_builds_inlined(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(BatchTranslator, "_client", staticmethod(lambda: fake))
    reqs = [{"key": "p0:v0", "model": "gemini-3.1-flash-lite", "temperature": 0.2,
             "prompt": "x"},
            {"key": "p0:v1", "model": "gemini-3.5-flash", "temperature": 0.4,
             "prompt": "y"}]
    job = BatchTranslator.submit(reqs)
    assert job == "batches/abc123"
    kw = fake.batches.created
    assert kw["model"] == "gemini-3.1-flash-lite"          # model top-level (bắt buộc)
    src = kw["src"]
    assert len(src) == 2
    # mỗi request mang model RIÊNG (trộn flash-lite/flash trong 1 job) + key ở metadata
    assert src[0]["model"] == "gemini-3.1-flash-lite"
    assert src[1]["model"] == "gemini-3.5-flash"
    assert src[0]["metadata"]["key"] == "p0:v0"
    assert src[0]["config"]["response_mime_type"] == "application/json"


def test_poll_returns_state(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(BatchTranslator, "_client", staticmethod(lambda: fake))
    assert BatchTranslator.poll("batches/abc123") == "JOB_STATE_RUNNING"


def test_poll_normalizes_enum_state_to_name(monkeypatch):
    """SDK trả enum JobState → poll phải trả STRING '.name' (endpoint so sánh str)."""
    import enum

    class JobState(enum.Enum):
        JOB_STATE_SUCCEEDED = "ok"

    class _B:
        def get(self, name):
            return type("J", (), {"state": JobState.JOB_STATE_SUCCEEDED})()

    class _C:
        batches = _B()
    monkeypatch.setattr(BatchTranslator, "_client", staticmethod(lambda: _C()))
    assert BatchTranslator.poll("batches/x") == "JOB_STATE_SUCCEEDED"


# ── Chốt kết quả batch: tái dùng judge/refine của harness với candidates có sẵn ──

def test_harmonize_accepts_pregenerated_candidates(monkeypatch):
    from backend.app.services.translation_harness import TranslationHarness
    blocks = [{"text": "Hello"}]
    cands = [["Xin chào"], ["Chào bạn"]]              # 2 ứng viên dựng sẵn (từ batch)
    monkeypatch.setattr(TranslationHarness, "_judge",
                        lambda b, c, lang, ctx: [{"best_idx": 0, "score": 90, "critique": "ok"}])
    # _generate_candidates KHÔNG được gọi khi đã cung cấp candidates
    monkeypatch.setattr(TranslationHarness, "_generate_candidates",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not generate")))
    res = TranslationHarness.harmonize_page(blocks, "vi", {}, [], candidates=cands)
    assert res is not None
    results, scores = res
    assert results == ["Xin chào"] and scores == [90]


def test_finalize_from_batch_builds_tm_rows(monkeypatch):
    """parse_map (key→candidates) + pages → list (source, translation, score) lưu TM."""
    from backend.app.services.translation_harness import TranslationHarness
    monkeypatch.setattr(TranslationHarness, "_judge",
                        lambda b, c, lang, ctx: [{"best_idx": 0, "score": 88, "critique": "ok"}
                                                 for _ in b])
    pages = [[{"text": "Hello"}, {"text": "World"}]]
    parsed = {"p0:v0": ["Xin chào", "Thế giới"], "p0:v1": ["Chào", "TG"]}
    rows = BatchTranslator.finalize(pages, parsed, "vi", {"domain": "general"}, [])
    assert ("Hello", "Xin chào", 88) in rows
    assert ("World", "Thế giới", 88) in rows


# ── Endpoint: ước tính (khách xem trước khi chọn) ──

def _make_pdf(path, pages=3):
    import fitz
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=300, height=400)
        pg.insert_text((20, 40), f"Page {i+1} content here", fontsize=12)
    doc.save(path); doc.close()


def test_estimate_endpoint_returns_both_modes(client, db_session, tmp_path):
    from backend.app.models_db import DBDocument
    from backend.app.core import DATA_DIR
    import os
    doc_id = "estdoc"
    raw = os.path.join(DATA_DIR, "raw_pdf"); os.makedirs(raw, exist_ok=True)
    _make_pdf(os.path.join(raw, f"{doc_id}.pdf"), pages=3)
    db_session.add(DBDocument(id=doc_id, filename="e.pdf", total_pages=3, status="extracted"))
    db_session.commit()
    r = client.get(f"/api/docs/{doc_id}/translate-estimate")
    assert r.status_code == 200
    j = r.json()
    assert j["pages"] == 3
    assert "online" in j and "batch" in j and "recommended_mode" in j
    assert j["recommendation"]
    os.remove(os.path.join(raw, f"{doc_id}.pdf"))


def test_fetch_results_returns_texts_in_order(monkeypatch):
    """inlined_responses → list text theo THỨ TỰ; response lỗi → '' (giữ vị trí)."""
    class _Resp:
        def __init__(self, t): self.text = t
    class _Item:
        def __init__(self, resp): self.response = resp
    class _Dest:
        inlined_responses = [
            _Item(_Resp('{"translations":[{"id":"b0","text":"X"}]}')),
            _Item(None),                                  # lỗi → giữ '' đúng vị trí
            _Item(_Resp("Y")),
        ]
    class _Job:
        dest = _Dest()
    class _B:
        def get(self, name): return _Job()
    class _C:
        batches = _B()
    monkeypatch.setattr(BatchTranslator, "_client", staticmethod(lambda: _C()))
    out = BatchTranslator.fetch_results("batches/x")
    assert out == ['{"translations":[{"id":"b0","text":"X"}]}', "", "Y"]
