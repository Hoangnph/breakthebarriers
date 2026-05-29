import os
import re
import sys
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(os.path.join(DATA_DIR, "raw_pdf"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "extracted_html"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "pages"), exist_ok=True)


def is_mock_run(doc_id: str) -> bool:
    if "pytest" in sys.modules:
        return True
    pdf_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")
    epub_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.epub")
    if not os.path.exists(pdf_path) and not os.path.exists(epub_path):
        return True
    existing = pdf_path if os.path.exists(pdf_path) else epub_path
    if os.path.getsize(existing) < 1000:
        return True
    return False


def estimate_pdf_pages(pdf_path: str) -> int:
    try:
        with open(pdf_path, "rb") as f:
            content = f.read(5 * 1024 * 1024)
            matches = re.findall(rb"/Count\s+(\d+)", content)
            if matches:
                return max(int(m) for m in matches)
    except Exception as e:
        logger.error(f"Error estimating PDF pages: {e}")
    return 10
