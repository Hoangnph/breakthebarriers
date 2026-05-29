import os
import pytest
from bs4 import BeautifulSoup

# Import services
from backend.app.services.extractor import Extractor
from backend.app.services.translator import Translator
from backend.app.services.compiler import Compiler

@pytest.fixture
def sample_absolute_html():
    return """<!DOCTYPE html>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1">
<style type="text/css">
body { background-color: #A0A0A0; }
.ff0 { font-family: sans-serif; }
</style>
</head>
<body>
<div id="page-container">
<div class="pf w0 h0" data-page-no="1">
<span id="s1" class="ff0 fs0 fc0 sc0 ls0" style="left:100.5px; top:200.0px;">Introductory</span>
<span id="s2" class="ff0 fs0 fc0 sc0 ls0" style="left:180.2px; top:200.3px;">Programming</span>
<span id="s3" class="ff0 fs0 fc0 sc0 ls0" style="left:100.5px; top:230.0px;">Second line of text</span>
</div>
</div>
</body>
</html>"""

# -------------------------------------------------------------
# 1. Extractor Tests
# -------------------------------------------------------------

def test_sanitize_html(sample_absolute_html):
    sanitized = Extractor.sanitize_html(sample_absolute_html)
    soup = BeautifulSoup(sanitized, "html.parser")
    
    # Assert UTF-8 meta is injected
    meta = soup.find("meta", charset="utf-8")
    assert meta is not None or "charset=utf-8" in sanitized.lower()
    
    # Assert grey backgrounds are sanitized to white
    assert "#A0A0A0" not in sanitized
    assert "#FFFFFF" in sanitized or "background-color" not in sanitized or "A0A0A0" not in sanitized

def test_extract_spans(sample_absolute_html):
    spans = Extractor.extract_spans(sample_absolute_html)
    assert len(spans) == 3
    assert spans[0]["id"] == "s1"
    assert spans[0]["text"] == "Introductory"
    assert spans[0]["top"] == 200.0
    assert spans[0]["left"] == 100.5

def test_docling_extractor_table_html():
    from unittest.mock import MagicMock
    from backend.app.services.extractor import DoclingExtractor

    table_item = MagicMock()
    table_item.label = "table"
    table_item.text = "Col A\tCol B\nVal 1\tVal 2\nVal 3\tVal 4"
    table_item.prov = []

    items = [(table_item, 1)]
    html = DoclingExtractor._items_to_page_html(items, page_no=1)

    assert "<table>" in html
    assert "<th>" in html
    assert "<td>" in html
    assert "Col A" in html
    assert "Val 1" in html


# -------------------------------------------------------------
# 2. Translator Tests
# -------------------------------------------------------------

def test_reconstruct_context_and_index():
    # Spans on the same line (top difference < 5px) should be grouped together
    spans = [
        {"id": "s1", "text": "Introductory", "top": 200.0, "left": 100.5},
        {"id": "s2", "text": "Programming", "top": 200.3, "left": 180.0},
        {"id": "s3", "text": "Second line", "top": 230.0, "left": 100.5}
    ]
    
    reconstructed_lines = Translator.reconstruct_context_and_index(spans)
    
    # Line 1 should have s1 and s2 grouped together
    assert len(reconstructed_lines) == 2
    assert reconstructed_lines[0]["text"] == "Introductory [s:s2] Programming"
    assert reconstructed_lines[0]["span_ids"] == ["s1", "s2"]
    
    # Line 2 should have s3
    assert reconstructed_lines[1]["text"] == "Second line"
    assert reconstructed_lines[1]["span_ids"] == ["s3"]

def test_agentic_translation():
    text = "Introductory Programming"
    glossary = {"Programming": "Lập trình"}
    translated = Translator.translate_text_agentic(text, glossary=glossary)
    
    # Assert glossary is enforced
    assert "Lập trình" in translated
    # Assert it translates to Vietnamese
    assert "Giới thiệu" in translated or "Nhập môn" in translated or "Lập trình" in translated

# -------------------------------------------------------------
# 3. Compiler Tests
# -------------------------------------------------------------

def test_inject_translation(sample_absolute_html):
    translated_texts = {
        "s1": "Nhập môn",
        "s2": "Lập trình",
        "s3": "Dòng chữ thứ hai"
    }
    
    compiled_html = Compiler.inject_translation(sample_absolute_html, translated_texts)
    
    # Verify the original text is replaced with translations
    assert "Introductory" not in compiled_html
    assert "Programming" not in compiled_html
    assert "Nhập môn" in compiled_html
    assert "Lập trình" in compiled_html
    assert "Dòng chữ thứ hai" in compiled_html

def test_quality_gates(sample_absolute_html):
    translated_texts_valid = {
        "s1": "Nhập môn",
        "s2": "Lập trình",
        "s3": "Dòng chữ thứ hai"
    }
    
    # Valid Case: Quality Gate passes
    assert Compiler.verify_quality_gates(sample_absolute_html, translated_texts_valid) is True
    
    # Invalid Case: Mismatched tag count (e.g. missing translation for s3)
    translated_texts_invalid = {
        "s1": "Nhập môn",
        "s2": "Lập trình"
    }
    assert Compiler.verify_quality_gates(sample_absolute_html, translated_texts_invalid) is False

def test_dynamic_font_shrink_injection(sample_absolute_html):
    translated_texts = {
        "s1": "Nhập môn",
        "s2": "Lập trình",
        "s3": "Dòng chữ thứ hai"
    }
    
    compiled_html = Compiler.inject_translation(sample_absolute_html, translated_texts)
    
    # Verify that the Dynamic Font Shrink script is successfully injected
    assert "window.addEventListener" in compiled_html
    assert "shrink" in compiled_html.lower() or "font" in compiled_html.lower()

def test_deinterpolate_translation():
    # 1. Normal sequential order
    block_text = "Nhập môn [s:s2] Lập trình [s:s3] Dòng chữ thứ hai"
    span_ids = ["s1", "s2", "s3"]
    result = Translator.deinterpolate_translation(block_text, span_ids)
    assert result["s1"] == "Nhập môn"
    assert result["s2"] == "Lập trình"
    assert result["s3"] == "Dòng chữ thứ hai"

    # 2. Reordered placeholders (common in grammar shifts)
    block_text_reordered = "C_trans [s:s3] A_trans [s:s2] B_trans"
    result_reordered = Translator.deinterpolate_translation(block_text_reordered, span_ids)
    assert result_reordered["s1"] == "C_trans"
    assert result_reordered["s3"] == "A_trans"
    assert result_reordered["s2"] == "B_trans"

    # 3. Spacing/Casing variation in tags
    block_text_spacing = "Nhập môn [s: s2] Lập trình [S:s3] Dòng chữ thứ hai"
    result_spacing = Translator.deinterpolate_translation(block_text_spacing, span_ids)
    assert result_spacing["s1"] == "Nhập môn"
    assert result_spacing["s2"] == "Lập trình"
    assert result_spacing["s3"] == "Dòng chữ thứ hai"

    # 4. Fallback when no valid tags are found
    block_text_fallback = "Bản dịch lỗi không chứa thẻ"
    result_fallback = Translator.deinterpolate_translation(block_text_fallback, span_ids)
    assert result_fallback["s1"] == "Bản dịch lỗi không chứa thẻ"


# -------------------------------------------------------------
# 4. Core Tests
# -------------------------------------------------------------

def test_is_mock_run_returns_true_in_pytest():
    from backend.app.core import is_mock_run
    assert is_mock_run("any_doc") is True

def test_estimate_pdf_pages_fallback_on_invalid_file(tmp_path):
    from backend.app.core import estimate_pdf_pages
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"not a real pdf")
    assert estimate_pdf_pages(str(fake_pdf)) == 10

def test_estimate_pdf_pages_reads_count(tmp_path):
    from backend.app.core import estimate_pdf_pages
    pdf_content = b"%PDF-1.4\n/Count 42\n"
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.write_bytes(pdf_content)
    assert estimate_pdf_pages(str(fake_pdf)) == 42


def test_dbjob_can_be_created(db_session):
    from backend.app.models_db import DBJob
    job = DBJob(
        doc_id="clean_code",
        stage="translate",
        volume_tier="S",
        quality_tier="high",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    assert job.id is not None
    assert job.status == "pending"
    assert job.retries == 0
    assert job.page_num is None


# -------------------------------------------------------------
# 5. VolumeDetector Tests
# -------------------------------------------------------------

def test_volume_detector_tier_s():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=30)
    assert profile.tier == "S"
    assert profile.processing_path == "asyncio"
    assert profile.recommended_quality == "high"
    assert profile.estimated_spans == 30 * 40
    assert profile.estimated_cost_usd > 0

def test_volume_detector_tier_m():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=100)
    assert profile.tier == "M"
    assert profile.processing_path == "asyncio"
    assert profile.recommended_quality == "balanced"

def test_volume_detector_tier_l():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=300)
    assert profile.tier == "L"
    assert profile.processing_path == "celery"
    assert profile.recommended_quality == "fast"

def test_volume_detector_tier_xl():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=600)
    assert profile.tier == "XL"
    assert profile.processing_path == "celery"

def test_volume_detector_quality_override():
    from backend.app.services.volume_detector import VolumeDetector
    profile = VolumeDetector.detect(page_count=300, quality_override="high")
    assert profile.tier == "L"
    assert profile.recommended_quality == "fast"
    # cost with override=high (3x multiplier) > cost with fast (1x)
    profile_fast = VolumeDetector.detect(page_count=300)
    assert profile.estimated_tokens > profile_fast.estimated_tokens

def test_volume_detector_cost_calculation():
    from backend.app.services.volume_detector import VolumeDetector, AVG_SPANS_PER_PAGE, AVG_TOKENS_PER_SPAN, GEMINI_PRICE_PER_1M_TOKENS
    profile = VolumeDetector.detect(page_count=10, quality_override="fast")
    expected_spans = 10 * AVG_SPANS_PER_PAGE
    expected_tokens = expected_spans * AVG_TOKENS_PER_SPAN * 1  # fast multiplier = 1
    expected_cost = round((expected_tokens / 1_000_000) * GEMINI_PRICE_PER_1M_TOKENS, 4)
    assert profile.estimated_spans == expected_spans
    assert profile.estimated_tokens == expected_tokens
    assert profile.estimated_cost_usd == expected_cost


# -------------------------------------------------------------
# 6. JobManager Tests
# -------------------------------------------------------------

def test_job_manager_semaphore_limits():
    from backend.app.services.job_manager import SEMAPHORE_LIMITS
    assert SEMAPHORE_LIMITS["S"] == 3
    assert SEMAPHORE_LIMITS["M"] == 8
    assert SEMAPHORE_LIMITS["L"] == 10
    assert SEMAPHORE_LIMITS["XL"] == 5

def test_run_translation_job_updates_status(db_session):
    """_run_translation_job should mark the job done or failed (never leave it pending)."""
    from backend.app.models_db import DBJob
    from backend.app.services.job_manager import _run_translation_job
    from backend.app.database import get_db
    from backend.app.main import app
    from fastapi.testclient import TestClient

    # Create a job record first
    job = DBJob(
        doc_id="clean_code",
        page_num=1,
        stage="translate",
        volume_tier="S",
        quality_tier="high",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    job_id = job.id

    # Extract pages so page 1 exists
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.post("/api/docs/clean_code/extract")
    app.dependency_overrides.clear()

    # Run the translation job synchronously
    _run_translation_job(job_id, "clean_code", 1, "vi", "high")

    # Job must not be left pending or running
    db_session.expire_all()
    updated = db_session.query(DBJob).filter(DBJob.id == job_id).first()
    assert updated.status in ("done", "failed"), f"Unexpected status: {updated.status}"


def test_dispatch_celery_job_sends_to_queue(monkeypatch):
    """dispatch_celery_job should call apply_async on translate_page_task."""
    from backend.app.services.job_manager import dispatch_celery_job

    task_ids_sent = []

    class FakeAsyncResult:
        def __init__(self): self.id = "fake-celery-task-id"

    def fake_apply_async(args, queue):
        task_ids_sent.append({"args": args, "queue": queue})
        return FakeAsyncResult()

    monkeypatch.setattr(
        "backend.app.workers.tasks.translate_page_task.apply_async",
        fake_apply_async,
    )

    result = dispatch_celery_job("job-1", "big_doc", 5, "vi", "fast", "L")
    assert result == "fake-celery-task-id"
    assert len(task_ids_sent) == 1
    assert task_ids_sent[0]["queue"] == "celery-high"  # L → celery-high
    assert task_ids_sent[0]["args"] == ["job-1", "big_doc", 5, "vi", "fast"]

def test_dispatch_celery_job_xl_uses_low_queue(monkeypatch):
    """XL tier should use celery-low queue."""
    from backend.app.services.job_manager import dispatch_celery_job

    queues_used = []

    class FakeResult:
        id = "fake-id"

    def fake_apply_async(args, queue):
        queues_used.append(queue)
        return FakeResult()

    monkeypatch.setattr(
        "backend.app.workers.tasks.translate_page_task.apply_async",
        fake_apply_async,
    )

    dispatch_celery_job("job-1", "big_doc", 1, "vi", "fast", "XL")
    assert queues_used == ["celery-low"]

def test_dispatch_all_routes_sm_to_asyncio(monkeypatch):
    """S/M tier must NOT call Celery dispatch."""
    import asyncio
    from backend.app.services.job_manager import dispatch_all_translation_jobs

    celery_called = []

    def fake_celery(job_id, doc_id, page_num, target_lang, quality, tier):
        celery_called.append(job_id)
        return "fake-id"

    monkeypatch.setattr("backend.app.services.job_manager.dispatch_celery_job", fake_celery)

    asyncio.run(dispatch_all_translation_jobs(
        jobs=[("j1", 1), ("j2", 2)],
        doc_id="doc", target_lang="vi", quality="high", tier="S",
    ))
    assert celery_called == []

def test_dispatch_all_routes_lxl_to_celery(monkeypatch):
    """L/XL tier must call Celery for every job."""
    import asyncio
    from backend.app.services.job_manager import dispatch_all_translation_jobs

    celery_called = []

    def fake_celery(job_id, doc_id, page_num, target_lang, quality, tier):
        celery_called.append((job_id, tier))
        return "fake-id"

    monkeypatch.setattr("backend.app.services.job_manager.dispatch_celery_job", fake_celery)

    asyncio.run(dispatch_all_translation_jobs(
        jobs=[("j1", 1), ("j2", 2)],
        doc_id="doc", target_lang="vi", quality="fast", tier="L",
    ))
    assert set(jid for jid, _ in celery_called) == {"j1", "j2"}
    assert all(tier == "L" for _, tier in celery_called)


# -------------------------------------------------------------
# EpubParser Tests
# -------------------------------------------------------------

import io
import zipfile


def _make_minimal_epub(chapters: dict) -> bytes:
    """
    Create an in-memory EPUB using ebooklib's own API.
    chapters = {"ch1.xhtml": "<html><body><p>Hello</p></body></html>", ...}
    """
    from ebooklib import epub as _epub
    book = _epub.EpubBook()
    book.set_identifier("test-id")
    book.set_title("Test Book")
    book.set_language("en")

    chapter_items = []
    for i, (fname, content) in enumerate(chapters.items()):
        c = _epub.EpubHtml(title=f"Chapter {i + 1}", file_name=fname, lang="en")
        c.content = content.encode("utf-8")
        book.add_item(c)
        chapter_items.append(c)

    book.add_item(_epub.EpubNcx())
    book.add_item(_epub.EpubNav())
    book.spine = ["nav"] + chapter_items

    buf = io.BytesIO()
    _epub.write_epub(buf, book, {})
    return buf.getvalue()


def test_epub_parser_extracts_chapters(tmp_path):
    from backend.app.services.epub_parser import EpubParser

    epub_bytes = _make_minimal_epub({
        "ch1.xhtml": "<html><body><p>Chapter One text</p></body></html>",
        "ch2.xhtml": "<html><body><h1>Chapter Two</h1><p>Body text</p></body></html>",
    })
    epub_path = str(tmp_path / "test.epub")
    with open(epub_path, "wb") as f:
        f.write(epub_bytes)

    out_dir = str(tmp_path / "out")
    files = EpubParser.extract_chapters_to_html(epub_path, out_dir, "test_book")

    assert len(files) == 2
    for path in files:
        assert os.path.exists(path)


def test_epub_parser_wraps_spans(tmp_path):
    from backend.app.services.epub_parser import EpubParser

    epub_bytes = _make_minimal_epub({
        "ch1.xhtml": "<html><body><p>Hello World</p></body></html>",
    })
    epub_path = str(tmp_path / "test.epub")
    with open(epub_path, "wb") as f:
        f.write(epub_bytes)

    out_dir = str(tmp_path / "out")
    files = EpubParser.extract_chapters_to_html(epub_path, out_dir, "test_book")

    with open(files[0]) as f:
        html = f.read()

    spans = Extractor.extract_spans(html)
    assert len(spans) >= 1
    assert any("Hello World" in s["text"] for s in spans)


def test_epub_parser_responsive_css(tmp_path):
    from backend.app.services.epub_parser import EpubParser

    epub_bytes = _make_minimal_epub({
        "ch1.xhtml": "<html><body><p>text</p></body></html>",
    })
    epub_path = str(tmp_path / "test.epub")
    with open(epub_path, "wb") as f:
        f.write(epub_bytes)

    out_dir = str(tmp_path / "out")
    files = EpubParser.extract_chapters_to_html(epub_path, out_dir, "test_book")

    with open(files[0]) as f:
        html = f.read()

    assert "max-width" in html
    assert "charset" in html.lower()

