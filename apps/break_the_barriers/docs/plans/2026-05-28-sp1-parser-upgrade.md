# SP1: Parser Upgrade — Docling + EPUB

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task.

**Goal:** Thay thế pdftohtml (absolute positioned HTML) bằng Docling — output HTML semantic, responsive, nhận diện heading/table/image. Thêm EPUB support.

**Architecture:** `DoclingExtractor` thay thế `Extractor.extract_pdf_to_html_cli()`. Backward-compatible: nếu Docling fail → fallback về pdftohtml. EPUB → extract chapters → same DBPage schema.

**Tech Stack:** Docling (IBM), ebooklib, pdf2image, BeautifulSoup, FastAPI (giữ nguyên)

---

## File Structure

```
backend/app/services/
├── extractor.py              MOD — thêm DoclingExtractor, EpubParser
├── html_normalizer.py        NEW — clean HTML, inject responsive CSS
backend/app/routers/
└── extraction.py             MOD — detect PDF vs EPUB, route đúng parser
backend/requirements.txt      MOD — thêm docling, ebooklib, pdf2image
```

---

## Task 1: Cài Docling + test compatibility

**Files:** `requirements.txt`

- [ ] **Step 1: Thêm dependencies vào requirements.txt**

```txt
docling>=2.0.0
ebooklib>=0.18
pdf2image>=1.17.0
```

- [ ] **Step 2: Cài và test Docling**

```bash
.venv/bin/pip install docling ebooklib pdf2image
.venv/bin/python -c "
from docling.document_converter import DocumentConverter
conv = DocumentConverter()
print('Docling OK:', conv)
"
```

Expected: `Docling OK: <DocumentConverter ...>`

- [ ] **Step 3: Test với PDF mẫu**

```bash
.venv/bin/python -c "
from docling.document_converter import DocumentConverter
conv = DocumentConverter()
result = conv.convert('backend/data/raw_pdf/clean_code.pdf')
html = result.document.export_to_html()
print('Pages:', len(result.document.pages))
print('HTML snippet:', html[:500])
"
```

Expected: HTML với `<h1>`, `<p>`, `<table>` thay vì `<span style=\"position:absolute\">`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add docling, ebooklib, pdf2image for parser upgrade"
```

---

## Task 2: DoclingExtractor service

**Files:**
- Create: `app/services/html_normalizer.py`
- Modify: `app/services/extractor.py`
- Modify: `tests/test_services.py`

- [ ] **Step 1: Viết tests**

Thêm vào `tests/test_services.py`:

```python
def test_html_normalizer_makes_responsive(tmp_path):
    from backend.app.services.html_normalizer import HtmlNormalizer
    raw_html = """<html><body>
    <span style="position:absolute;left:100px;top:200px;">Hello</span>
    </body></html>"""
    result = HtmlNormalizer.normalize(raw_html)
    assert "position:absolute" not in result
    assert "max-width" in result or "margin" in result

def test_docling_extractor_returns_html_list(tmp_path):
    from backend.app.services.extractor import DoclingExtractor
    import os
    # Dùng PDF mẫu nhỏ nếu có, không thì skip
    pdf_path = "backend/data/raw_pdf/clean_code.pdf"
    if not os.path.exists(pdf_path):
        import pytest; pytest.skip("No sample PDF available")
    pages = DoclingExtractor.extract(pdf_path, str(tmp_path), "clean_code")
    assert isinstance(pages, list)
    assert len(pages) > 0
    assert all("<" in p for p in pages)  # là HTML
```

- [ ] **Step 2: Tạo app/services/html_normalizer.py**

```python
import re
from bs4 import BeautifulSoup

RESPONSIVE_CSS = """
<style>
.book-page {
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
    font-family: Georgia, serif;
    line-height: 1.8;
    color: #1a1a1a;
}
.book-page h1, .book-page h2, .book-page h3 {
    font-weight: bold;
    margin: 1.5em 0 0.5em;
}
.book-page p { margin: 0.8em 0; }
.book-page table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
}
.book-page td, .book-page th {
    border: 1px solid #ddd;
    padding: 8px;
}
.book-page img { max-width: 100%; height: auto; }
.book-page figure { margin: 1em 0; text-align: center; }
</style>
"""

class HtmlNormalizer:
    @staticmethod
    def normalize(html: str, doc_id: str = "", page_num: int = 0) -> str:
        """Remove absolute positioning, inject responsive CSS, wrap in .book-page."""
        # Remove position:absolute inline styles
        cleaned = re.sub(
            r'style="[^"]*position\s*:\s*absolute[^"]*"',
            '',
            html,
            flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r"style='[^']*position\s*:\s*absolute[^']*'",
            '',
            cleaned,
            flags=re.IGNORECASE
        )

        soup = BeautifulSoup(cleaned, "html.parser")

        # Inject responsive CSS into <head>
        head = soup.find("head")
        if not head:
            head = soup.new_tag("head")
            if soup.html:
                soup.html.insert(0, head)

        style_tag = BeautifulSoup(RESPONSIVE_CSS, "html.parser")
        head.append(style_tag)

        # Wrap body content in .book-page div
        body = soup.find("body")
        if body:
            wrapper = soup.new_tag("div", attrs={"class": "book-page"})
            for child in list(body.children):
                wrapper.append(child.extract())
            body.append(wrapper)

        return str(soup)
```

- [ ] **Step 3: Thêm DoclingExtractor vào app/services/extractor.py**

Thêm class mới vào cuối `extractor.py`:

```python
class DoclingExtractor:
    """High-quality PDF extractor using Docling (IBM). Produces semantic HTML."""

    @staticmethod
    def extract(pdf_path: str, output_dir: str, doc_id: str) -> list[str]:
        """
        Convert PDF to list of HTML strings (1 per page) using Docling.
        Falls back to legacy pdftohtml if Docling fails.
        Returns: list of HTML strings, one per page.
        """
        import os
        from backend.app.services.html_normalizer import HtmlNormalizer

        try:
            from docling.document_converter import DocumentConverter
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions

            options = PdfPipelineOptions()
            options.do_ocr = False          # skip OCR for speed
            options.do_table_structure = True

            conv = DocumentConverter()
            result = conv.convert(pdf_path)
            doc = result.document

            pages_html = []
            total_pages = len(doc.pages)

            for page_no in range(1, total_pages + 1):
                # Export single page as HTML
                page_html = doc.export_to_html(page_no=page_no)

                if not page_html:
                    # Fallback: export markdown → wrap in HTML
                    page_md = doc.export_to_markdown(page_no=page_no)
                    page_html = f"<html><body><div>{page_md}</div></body></html>"

                normalized = HtmlNormalizer.normalize(page_html, doc_id, page_no)
                pages_html.append(normalized)

            logger.info(f"Docling extracted {len(pages_html)} pages from {pdf_path}")
            return pages_html

        except ImportError:
            logger.warning("Docling not available, falling back to pdftohtml")
            return DoclingExtractor._fallback_extract(pdf_path, output_dir, doc_id)
        except Exception as e:
            logger.error(f"Docling failed: {e}. Falling back to pdftohtml")
            return DoclingExtractor._fallback_extract(pdf_path, output_dir, doc_id)

    @staticmethod
    def _fallback_extract(pdf_path: str, output_dir: str, doc_id: str) -> list[str]:
        """Legacy pdftohtml fallback."""
        from backend.app.services.html_normalizer import HtmlNormalizer
        html_files = Extractor.extract_pdf_to_html_cli(pdf_path, output_dir, doc_id)
        pages = []
        for f in html_files:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                raw = fh.read()
            pages.append(HtmlNormalizer.normalize(raw))
        return pages
```

- [ ] **Step 4: Chạy tests**

```bash
.venv/bin/pytest tests/test_services.py -k "normalizer or docling" -v
```

Expected: `test_html_normalizer_makes_responsive` PASS, docling test PASS hoặc SKIP

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

Expected: 54+ passed

- [ ] **Step 6: Commit**

```bash
git add app/services/html_normalizer.py app/services/extractor.py tests/test_services.py
git commit -m "feat: add DoclingExtractor and HtmlNormalizer for responsive HTML output"
```

---

## Task 3: EPUB Parser

**Files:**
- Create: `app/services/epub_parser.py`
- Modify: `app/routers/extraction.py`
- Modify: `tests/test_services.py`

- [ ] **Step 1: Viết test**

Thêm vào `tests/test_services.py`:

```python
def test_epub_parser_detects_epub(tmp_path):
    from backend.app.services.epub_parser import EpubParser
    # Tạo mock EPUB (ZIP với mimetype)
    import zipfile, os
    epub_path = str(tmp_path / "test.epub")
    with zipfile.ZipFile(epub_path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("OEBPS/content.opf", """<?xml version="1.0"?>
<package><metadata/><manifest>
<item id="ch1" href="ch1.html" media-type="application/xhtml+xml"/>
</manifest><spine><itemref idref="ch1"/></spine></package>""")
        z.writestr("OEBPS/ch1.html",
            "<html><body><h1>Chapter 1</h1><p>Content here.</p></body></html>")
    pages = EpubParser.extract(epub_path)
    assert len(pages) >= 1
    assert "Chapter 1" in pages[0]
```

- [ ] **Step 2: Tạo app/services/epub_parser.py**

```python
import zipfile
import logging
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List

logger = logging.getLogger(__name__)


class EpubParser:
    @staticmethod
    def extract(epub_path: str) -> List[str]:
        """
        Extract EPUB → list of HTML strings (one per chapter/spine item).
        EPUB is a ZIP containing XHTML files. We read the spine order from OPF.
        """
        from backend.app.services.html_normalizer import HtmlNormalizer

        pages_html = []

        with zipfile.ZipFile(epub_path, "r") as z:
            # 1. Find OPF manifest file
            container_xml = z.read("META-INF/container.xml").decode("utf-8", errors="ignore")
            soup = BeautifulSoup(container_xml, "xml")
            opf_path = soup.find("rootfile").get("full-path", "OEBPS/content.opf")
            opf_dir = str(Path(opf_path).parent)

            # 2. Parse OPF for spine order
            opf_content = z.read(opf_path).decode("utf-8", errors="ignore")
            opf_soup = BeautifulSoup(opf_content, "xml")

            # Build id→href map from manifest
            manifest = {}
            for item in opf_soup.find_all("item"):
                media_type = item.get("media-type", "")
                if "xhtml" in media_type or "html" in media_type:
                    manifest[item.get("id")] = item.get("href", "")

            # Read spine order
            spine = [ref.get("idref") for ref in opf_soup.find_all("itemref")]

            # 3. Extract each spine item as HTML
            for item_id in spine:
                href = manifest.get(item_id)
                if not href:
                    continue

                # Resolve path relative to OPF location
                full_path = f"{opf_dir}/{href}" if opf_dir and opf_dir != "." else href

                try:
                    content = z.read(full_path).decode("utf-8", errors="ignore")
                except KeyError:
                    logger.warning(f"EPUB: cannot find {full_path}")
                    continue

                normalized = HtmlNormalizer.normalize(content)
                pages_html.append(normalized)

        logger.info(f"EPUB extracted {len(pages_html)} chapters from {epub_path}")
        return pages_html
```

- [ ] **Step 3: Update extraction router để detect file type**

Trong `app/routers/extraction.py`, cập nhật `_perform_extraction` phần real run (không phải mock):

```python
# Detect file type
pdf_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")
epub_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.epub")

if os.path.exists(epub_path):
    # EPUB path
    from backend.app.services.epub_parser import EpubParser
    pages_html_list = EpubParser.extract(epub_path)
    html_files = None
else:
    # PDF path — try Docling first, fallback to pdftohtml
    from backend.app.services.extractor import DoclingExtractor
    extracted_dir = os.path.join(DATA_DIR, "extracted_html", doc_id)
    pages_html_list = DoclingExtractor.extract(pdf_path, extracted_dir, doc_id)
    html_files = None

if html_files is not None and html_files:
    doc.total_pages = len(html_files)
elif pages_html_list:
    doc.total_pages = len(pages_html_list)
```

- [ ] **Step 4: Update upload endpoint để accept .epub**

Trong `app/routers/documents.py`, sửa validation:

```python
if not (file.filename.endswith(".pdf") or file.filename.endswith(".epub")):
    raise HTTPException(status_code=400, detail="Only PDF and EPUB files are supported")
```

- [ ] **Step 5: Chạy tests**

```bash
.venv/bin/pytest tests/test_services.py -k "epub" -v
.venv/bin/pytest tests/ -q 2>&1 | tail -3
```

Expected: epub test PASS, tất cả tests pass

- [ ] **Step 6: Commit**

```bash
git add app/services/epub_parser.py app/routers/extraction.py app/routers/documents.py tests/test_services.py
git commit -m "feat: add EPUB parser, detect PDF/EPUB file type in extraction pipeline"
```

---

## Task 4: Update Docker image với Docling

**Files:** `Dockerfile`, `docker-compose.dev.yml`

- [ ] **Step 1: Rebuild image**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/break_the_barriers
docker compose -f docker-compose.yml -f docker-compose.dev.yml build app worker
```

Docling cần ~500MB deps (torch models). Expected build time: 5-10 phút.

- [ ] **Step 2: Test trong container**

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec app \
  python -c "from docling.document_converter import DocumentConverter; print('Docling OK')"
```

- [ ] **Step 3: Verify API vẫn hoạt động**

```bash
curl -s http://localhost:8000/ | python3 -m json.tool
```

- [ ] **Step 4: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/Dockerfile apps/break_the_barriers/backend/requirements.txt
git commit -m "build: update Docker image with Docling, ebooklib, pdf2image"
```

---

## Checklist SP1 hoàn thành

- [ ] Docling cài được, test với PDF mẫu
- [ ] `DoclingExtractor.extract()` trả về semantic HTML (h1/p/table)
- [ ] `HtmlNormalizer.normalize()` loại bỏ `position:absolute`
- [ ] `EpubParser.extract()` trả về chapters HTML
- [ ] Upload endpoint accept `.epub`
- [ ] Extraction router detect PDF vs EPUB
- [ ] Docker image build được với Docling
- [ ] 54+ tests pass

**Tiếp theo:** SP2 — SaaS Platform (auth + billing + multi-tenant)
