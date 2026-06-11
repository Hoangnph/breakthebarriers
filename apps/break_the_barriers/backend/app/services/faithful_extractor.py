"""PDF → faithful SVG (Gốc) + text layer + reflow HTML (Dịch) per page.

Ghi cạnh nhau trong output_dir:
  {doc}-{n}.svg  (hoặc .jpg fallback) — visual nền trung thực
  {doc}-{n}.textlayer.json            — lớp text vô hình (copy/select)
  {doc}-{n}.html                      — reflow HTML có span id (nguồn dịch + nền Dịch)
Trả list path .html theo thứ tự trang (cùng interface extractor cũ)."""
import os
import json
import html as html_lib
import logging
from pathlib import Path
from collections import defaultdict
from typing import List, Optional
import fitz

from backend.app.services.text_layer import build_text_layer, reflow_blocks

logger = logging.getLogger(__name__)

_REFLOW_CSS = """
body{font-family:Arial,sans-serif;line-height:1.7;max-width:800px;margin:0 auto;padding:1.5rem;color:#333}
h1,h2,h3,h4,h5,h6{margin-top:1.4em;margin-bottom:.4em;line-height:1.3}
p{margin:.6em 0} ul,ol{padding-left:1.6em} li{margin:.3em 0}
table{border-collapse:collapse;width:100%;margin:1em 0} th,td{border:1px solid #ddd;padding:8px 12px;text-align:left}
th{background:#f2f2f2;font-weight:bold}
"""

_converter = None


class FaithfulExtractor:

    @classmethod
    def extract_pdf(cls, pdf_path: str, output_dir: str, doc_id: str) -> List[str]:
        os.makedirs(output_dir, exist_ok=True)
        doc = fitz.open(pdf_path)
        docling_pages = cls._docling_structure(pdf_path)  # {page_no: [(item,level)]} | None

        html_files: List[str] = []
        for i in range(len(doc)):
            page_no = i + 1
            page = doc[i]
            base = os.path.join(output_dir, f"{doc_id}-{page_no}")

            # Per-page guard: one bad page degrades to a placeholder reflow page
            # (no .svg/.textlayer → goc view falls back gracefully) without aborting
            # the whole document. Always append base+".html" to keep page_num aligned.
            try:
                cls._render_visual(page, output_dir, doc_id, page_no)

                with open(base + ".textlayer.json", "w", encoding="utf-8") as f:
                    json.dump(build_text_layer(page), f)

                if docling_pages and docling_pages.get(page_no):
                    body = cls._docling_items_to_body(docling_pages[page_no])
                else:
                    body = cls._blocks_to_body(reflow_blocks(page))
                with open(base + ".html", "w", encoding="utf-8") as f:
                    f.write(cls._wrap_doc(body))
            except Exception as e:
                logger.warning(f"Faithful extract failed p{page_no}, placeholder: {e}")
                with open(base + ".html", "w", encoding="utf-8") as f:
                    f.write(cls._wrap_doc(f'<p><span id="s1">[page {page_no}]</span></p>'))
            html_files.append(base + ".html")

        doc.close()
        return html_files

    @staticmethod
    def _render_visual(page, output_dir: str, doc_id: str, page_no: int) -> str:
        try:
            svg = page.get_svg_image()
            name = f"{doc_id}-{page_no}.svg"
            with open(os.path.join(output_dir, name), "w", encoding="utf-8") as f:
                f.write(svg)
            return name
        except Exception as e:
            logger.warning(f"SVG render failed p{page_no}, raster fallback: {e}")
            name = f"{doc_id}-{page_no}.jpg"
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            pix.save(os.path.join(output_dir, name))
            return name

    @staticmethod
    def _docling_structure(pdf_path: str) -> Optional[dict]:
        global _converter
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice)
            if _converter is None:
                opts = PdfPipelineOptions()
                opts.do_ocr = False
                opts.generate_page_images = False
                opts.accelerator_options = AcceleratorOptions(
                    num_threads=4, device=AcceleratorDevice.CPU)
                _converter = DocumentConverter(
                    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
            result = _converter.convert(Path(pdf_path))
            pages = defaultdict(list)
            for item, level in result.document.iterate_items():
                if hasattr(item, "prov") and item.prov:
                    pages[item.prov[0].page_no].append((item, level))
            return pages
        except Exception as e:
            logger.warning(f"Docling structure failed, fallback to PyMuPDF reflow: {e}")
            return None

    @staticmethod
    def _docling_items_to_body(items) -> str:
        parts: List[str] = []
        counter = [0]
        open_list = False

        def wrap(text: str) -> str:
            counter[0] += 1
            return f'<span id="s{counter[0]}">{html_lib.escape(text)}</span>'

        for item, level in items:
            text = (getattr(item, "text", "") or "").strip()
            label = str(getattr(item, "label", "text"))
            if label == "list_item":
                if not open_list:
                    parts.append("<ul>"); open_list = True
                if text:
                    parts.append(f"<li>{wrap(text)}</li>")
                continue
            if open_list:
                parts.append("</ul>"); open_list = False
            if not text:
                continue
            if label == "section_header":
                h = min(max(level + 1, 2), 6)
                parts.append(f"<h{h}>{wrap(text)}</h{h}>")
            elif label == "table":
                parts.append(FaithfulExtractor._table_to_html(text, wrap))
            else:
                parts.append(f"<p>{wrap(text)}</p>")
        if open_list:
            parts.append("</ul>")
        return "\n".join(parts)

    @staticmethod
    def _blocks_to_body(blocks) -> str:
        parts: List[str] = []
        for i, b in enumerate(blocks, start=1):
            span = f'<span id="s{i}">{html_lib.escape(b["text"])}</span>'
            if b.get("role") == "heading":
                parts.append(f"<h2>{span}</h2>")
            else:
                parts.append(f"<p>{span}</p>")
        return "\n".join(parts)

    @staticmethod
    def _table_to_html(text: str, wrap) -> str:
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        if not lines or "\t" not in lines[0]:
            return f"<p>{wrap(text)}</p>"
        rows = [ln.split("\t") for ln in lines]
        head = "".join(f"<th>{wrap(c.strip())}</th>" for c in rows[0])
        body = "".join(
            "<tr>" + "".join(f"<td>{wrap(c.strip())}</td>" for c in r) + "</tr>"
            for r in rows[1:])
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    @staticmethod
    def _wrap_doc(body: str) -> str:
        return (
            "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"<style>\n{_REFLOW_CSS}\n</style>\n</head>\n<body>\n"
            + body + "\n</body>\n</html>")
