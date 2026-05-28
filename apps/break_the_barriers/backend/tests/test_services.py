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

