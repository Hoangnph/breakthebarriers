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


def test_parse_batch_results_maps_keys_to_id_text_map():
    """Kết quả batch (key → JSON translations) → {key: {id: text}} (giữ id để
    align theo số block khi chốt)."""
    raw = [
        {"key": "p0:v0",
         "text": '{"translations":[{"id":"b0","text":"Xin chào"},{"id":"b1","text":"Khối hai"}]}'},
        {"key": "p1:v0", "text": '{"translations":[{"id":"b0","text":"Trang hai"}]}'},
    ]
    out = BatchTranslator.parse_batch_results(raw)
    assert out["p0:v0"] == {"b0": "Xin chào", "b1": "Khối hai"}
    assert out["p1:v0"] == {"b0": "Trang hai"}


def test_parse_batch_results_skips_malformed():
    raw = [{"key": "p0:v0", "text": "not json"},
           {"key": "p0:v1", "text": '{"translations":[{"id":"b0","text":"OK"}]}'}]
    out = BatchTranslator.parse_batch_results(raw)
    assert "p0:v0" not in out
    assert out["p0:v1"] == {"b0": "OK"}


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


class _SeqBatches:
    """create() trả job tên tăng dần để phân biệt nhiều job (group theo model)."""
    def __init__(self):
        self.calls = []
        self.n = 0

    def create(self, **kw):
        self.calls.append(kw)
        self.n += 1
        return type("J", (), {"name": f"batches/job{self.n}"})()


class _SeqClient:
    def __init__(self):
        self.batches = _SeqBatches()


def test_submit_groups_by_model_one_job_per_model(monkeypatch):
    """Gemini Batch BẮT BUỘC 1 model/job → group theo model: flash-lite (v0) và
    flash (v1,v2) thành 2 job; mỗi job giữ keys theo thứ tự để map kết quả."""
    fake = _SeqClient()
    monkeypatch.setattr(BatchTranslator, "_client", staticmethod(lambda: fake))
    reqs = [
        {"key": "p0:v0", "model": "gemini-3.1-flash-lite", "temperature": 0.2, "prompt": "a"},
        {"key": "p0:v1", "model": "gemini-3.5-flash", "temperature": 0.4, "prompt": "b"},
        {"key": "p0:v2", "model": "gemini-3.5-flash", "temperature": 0.7, "prompt": "c"},
    ]
    jobs = BatchTranslator.submit(reqs)
    assert len(jobs) == 2                               # 2 model → 2 job
    by_model = {c["model"]: c for c in fake.batches.calls}
    # mỗi job CHỈ chứa request đúng model của nó
    assert all(r["model"] == "gemini-3.1-flash-lite"
               for r in by_model["gemini-3.1-flash-lite"]["src"])
    assert len(by_model["gemini-3.5-flash"]["src"]) == 2
    # keys lưu theo job để map text→key
    lite_job = next(j for j in jobs if j["model"] == "gemini-3.1-flash-lite")
    assert lite_job["keys"] == ["p0:v0"]
    flash_job = next(j for j in jobs if j["model"] == "gemini-3.5-flash")
    assert flash_job["keys"] == ["p0:v1", "p0:v2"]


def test_aggregate_state_all_succeeded_else_pending(monkeypatch):
    agg = BatchTranslator.aggregate_state
    assert agg(["JOB_STATE_SUCCEEDED", "JOB_STATE_SUCCEEDED"]) == "JOB_STATE_SUCCEEDED"
    assert agg(["JOB_STATE_SUCCEEDED", "JOB_STATE_RUNNING"]) == "JOB_STATE_RUNNING"
    # bất kỳ job lỗi → tổng = lỗi
    assert agg(["JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED"]) == "JOB_STATE_FAILED"
    assert agg(["JOB_STATE_EXPIRED", "JOB_STATE_SUCCEEDED"]) == "JOB_STATE_EXPIRED"


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
    """parse_map (key→{id:text}) + pages → list (source, translation, score) lưu TM."""
    from backend.app.services.translation_harness import TranslationHarness
    monkeypatch.setattr(TranslationHarness, "_judge",
                        lambda b, c, lang, ctx: [{"best_idx": 0, "score": 88, "critique": "ok"}
                                                 for _ in b])
    pages = [[{"text": "Hello"}, {"text": "World"}]]
    parsed = {"p0:v0": {"b0": "Xin chào", "b1": "Thế giới"},
              "p0:v1": {"b0": "Chào", "b1": "TG"}}
    rows = BatchTranslator.finalize(pages, parsed, "vi", {"domain": "general"}, [])
    assert ("Hello", "Xin chào", 88) in rows
    assert ("World", "Thế giới", 88) in rows


def test_finalize_skips_untranslated_blocks(monkeypatch):
    """Block mà MỌI ứng viên đều fallback source (==English) → KHÔNG lưu TM (tránh
    nhuộm English; htmlflow tự fallback source). Chỉ lưu bản dịch thật."""
    from backend.app.services.translation_harness import TranslationHarness
    monkeypatch.setattr(TranslationHarness, "_judge",
                        lambda b, c, lang, ctx: [{"best_idx": 0, "score": 80, "critique": "ok"}
                                                 for _ in b])
    pages = [[{"text": "Hello"}, {"text": "Untranslated"}]]
    # b1 thiếu ở mọi variant → fallback "Untranslated" (==source) → bỏ
    parsed = {"p0:v0": {"b0": "Xin chào"}}
    rows = BatchTranslator.finalize(pages, parsed, "vi", {"domain": "general"}, [])
    srcs = {r[0] for r in rows}
    assert "Hello" in srcs
    assert "Untranslated" not in srcs        # KHÔNG lưu block còn nguyên English


def test_finalize_aligns_candidate_when_model_returns_fewer(monkeypatch):
    """LỖI THẬT: model trả ÍT bản dịch hơn số block (gộp/tách) → KHÔNG loại trang;
    align theo số block, id thiếu → fallback source (như đường online)."""
    from backend.app.services.translation_harness import TranslationHarness
    monkeypatch.setattr(TranslationHarness, "_judge",
                        lambda b, c, lang, ctx: [{"best_idx": 0, "score": 85, "critique": "ok"}
                                                 for _ in b])
    pages = [[{"text": "Hello"}, {"text": "World"}, {"text": "Three"}]]   # 3 block
    # model chỉ trả b0,b1 (thiếu b2) → trang KHÔNG bị bỏ; b0,b1 dịch, b2 (chưa
    # dịch) bỏ qua lưu — KHÁC hẳn cũ (mismatch len → rớt CẢ trang).
    parsed = {"p0:v0": {"b0": "Xin chào", "b1": "Thế giới"}}
    rows = BatchTranslator.finalize(pages, parsed, "vi", {"domain": "general"}, [])
    srcs = {r[0] for r in rows}
    assert "Hello" in srcs and "World" in srcs        # 2 block dịch được giữ
    assert "Three" not in srcs                         # block chưa dịch → bỏ
    assert ("Hello", "Xin chào", 85) in rows


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


# ── Auto-poll nền + chốt idempotent (tránh judge/refine 2 lần = tốn phí) ──

def test_finalize_into_tm_is_idempotent(client, db_session, monkeypatch, tmp_path):
    """Chốt lần 1 → lưu TM + đánh dấu done; lần 2 → BỎ QUA (không chốt lại)."""
    import os, json
    from backend.app.models_db import DBDocument
    from backend.app.core import DATA_DIR
    from backend.app.routers import documents as docs
    from backend.app.services.translation_batch import BatchTranslator
    from backend.app.services.translation_harness import TranslationHarness

    doc_id = "batchfin"
    raw = os.path.join(DATA_DIR, "raw_pdf"); os.makedirs(raw, exist_ok=True)
    _make_pdf(os.path.join(raw, f"{doc_id}.pdf"), pages=1)
    db_session.add(DBDocument(id=doc_id, filename="b.pdf", total_pages=1, status="extracted"))
    db_session.commit()
    group = "batches/jobA"
    # group gồm 2 job (group theo model): lite (v0) + flash (v1,v2)
    with open(docs._batch_job_path(group), "w") as f:
        json.dump({"doc_id": doc_id, "lang": "vi", "quality": "max", "status": "submitted",
                   "jobs": [{"job": "batches/jobA", "model": "gemini-3.1-flash-lite",
                             "keys": ["p0:v0"]},
                            {"job": "batches/jobB", "model": "gemini-3.5-flash",
                             "keys": ["p0:v1", "p0:v2"]}]}, f)

    monkeypatch.setattr(TranslationHarness, "_judge",
                        lambda b, c, lang, ctx: [{"best_idx": 0, "score": 95, "critique": "ok"} for _ in b])
    calls = {"fetch": 0}
    def fake_fetch(jn):
        calls["fetch"] += 1
        return ['{"translations":[{"id":"b0","text":"NỘI DUNG TRANG"}]}']  # mỗi job 1 key→1 text
    monkeypatch.setattr(BatchTranslator, "fetch_results", staticmethod(fake_fetch))

    r1 = docs._finalize_batch_into_tm(group, db_session)
    assert r1["status"] == "done" and r1["translated_blocks"] >= 1
    r2 = docs._finalize_batch_into_tm(group, db_session)
    assert r2.get("skipped") is True          # lần 2 bỏ qua
    assert calls["fetch"] == 2                 # 2 job fetch ở lần 1; lần 2 KHÔNG fetch lại
    os.remove(os.path.join(raw, f"{doc_id}.pdf"))


def _write_group_meta(docs, group, jobs_states):
    """Ghi sidecar group với danh sách job (chưa done)."""
    import json
    jobs = [{"job": f"batches/j{i}", "model": "m", "keys": ["p0:v0"]}
            for i in range(len(jobs_states))]
    with open(docs._batch_job_path(group), "w") as f:
        json.dump({"doc_id": "d1", "lang": "vi", "status": "submitted", "jobs": jobs}, f)


def test_run_batch_poll_bg_finalizes_on_success(monkeypatch):
    """Poller: poll tới khi TẤT CẢ job SUCCEEDED → finalize đúng 1 lần rồi dừng."""
    from backend.app.routers import documents as docs
    from backend.app.services.translation_batch import BatchTranslator
    group = "batches/grpOK"
    _write_group_meta(docs, group, ["x"])      # 1 job trong group
    states = iter(["JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_SUCCEEDED"])
    monkeypatch.setattr(BatchTranslator, "poll", staticmethod(lambda j: next(states)))
    monkeypatch.setattr(docs.time, "sleep", lambda s: None)
    monkeypatch.setattr(docs, "get_background_db", lambda: _DummyDB())
    fin = {"n": 0}
    monkeypatch.setattr(docs, "_finalize_batch_into_tm",
                        lambda group_id, db: fin.__setitem__("n", fin["n"] + 1) or {"status": "done"})
    docs.run_batch_poll_bg(group, interval=0, max_seconds=100)
    assert fin["n"] == 1


def test_run_batch_poll_bg_stops_on_failure(monkeypatch):
    from backend.app.routers import documents as docs
    from backend.app.services.translation_batch import BatchTranslator
    group = "batches/grpFail"
    _write_group_meta(docs, group, ["x"])
    monkeypatch.setattr(BatchTranslator, "poll", staticmethod(lambda j: "JOB_STATE_FAILED"))
    monkeypatch.setattr(docs.time, "sleep", lambda s: None)
    monkeypatch.setattr(docs, "get_background_db", lambda: _DummyDB())
    fin = {"n": 0}
    monkeypatch.setattr(docs, "_finalize_batch_into_tm",
                        lambda *a: fin.__setitem__("n", fin["n"] + 1))
    docs.run_batch_poll_bg(group, interval=0, max_seconds=100)
    assert fin["n"] == 0                        # job lỗi → KHÔNG chốt


class _DummyDB:
    def close(self): pass
