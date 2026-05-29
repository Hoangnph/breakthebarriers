import os
import html as html_lib
import logging
from typing import List
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_EPUB_RESPONSIVE_CSS = """
* { box-sizing: border-box; }
body {
    font-family: Georgia, serif;
    line-height: 1.8;
    max-width: 800px;
    margin: 0 auto;
    padding: 1.5rem;
    color: #222;
}
h1, h2, h3, h4, h5, h6 {
    margin-top: 1.4em;
    margin-bottom: 0.4em;
    line-height: 1.3;
    font-family: Arial, sans-serif;
}
p { margin: 0.7em 0; text-indent: 1.2em; }
p:first-child { text-indent: 0; }
ul, ol { padding-left: 1.6em; }
li { margin: 0.3em 0; }
img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
blockquote {
    border-left: 3px solid #ccc;
    margin: 1em 0;
    padding: 0 1em;
    color: #555;
    font-style: italic;
}
"""


class EpubParser:
    """Extract chapters from an EPUB file into per-chapter semantic HTML files."""

    @classmethod
    def extract_chapters_to_html(
        cls, epub_path: str, output_dir: str, doc_id: str
    ) -> List[str]:
        """
        Open an EPUB, extract each spine chapter as a clean HTML file with
        translatable <span id="sN"> wrappers. Returns file paths in spine order.
        Same interface as DoclingExtractor.extract_pdf_to_html().
        """
        try:
            from ebooklib import epub, ITEM_DOCUMENT
        except ImportError:
            raise RuntimeError("ebooklib is not installed. Run: pip install ebooklib")

        os.makedirs(output_dir, exist_ok=True)
        book = epub.read_epub(epub_path, options={"ignore_ncx": True})

        # Follow spine order; exclude the EPUB3 nav document (EpubNav instance)
        spine_ids = {item_id for item_id, _ in book.spine}
        chapters = [
            item for item in book.get_items_of_type(ITEM_DOCUMENT)
            if item.get_id() in spine_ids and not isinstance(item, epub.EpubNav)
        ]

        if not chapters:
            # Fallback: use all non-nav document items if spine lookup fails
            chapters = [
                item for item in book.get_items_of_type(ITEM_DOCUMENT)
                if not isinstance(item, epub.EpubNav)
            ]

        html_files: List[str] = []
        for idx, chapter in enumerate(chapters, start=1):
            raw_html = chapter.get_content().decode("utf-8", errors="replace")
            page_html = cls._render_chapter(raw_html, idx)
            file_path = os.path.join(output_dir, f"{doc_id}-{idx}.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(page_html)
            html_files.append(file_path)

        logger.info(f"EpubParser: extracted {len(html_files)} chapters from {epub_path}")
        return html_files

    @staticmethod
    def _render_chapter(raw_html: str, chapter_num: int) -> str:
        """
        Parse one EPUB chapter's XHTML, wrap each paragraph/heading text
        in <span id="sN"> for translation, inject responsive CSS.
        """
        soup = BeautifulSoup(raw_html, "html.parser")
        body = soup.find("body") or soup

        span_counter = [0]

        def next_sid() -> str:
            span_counter[0] += 1
            return f"s{span_counter[0]}"

        translatable_tags = {
            "p", "h1", "h2", "h3", "h4", "h5", "h6",
            "li", "td", "th", "blockquote",
        }
        parts: List[str] = []

        for tag in body.find_all(translatable_tags):
            text = tag.get_text(separator=" ").strip()
            if not text:
                continue
            sid = next_sid()
            parts.append(
                f"<{tag.name}><span id=\"{sid}\">{html_lib.escape(text)}</span></{tag.name}>"
            )

        if not parts:
            # Chapter has no recognisable text tags — wrap whole body text
            text = body.get_text(separator=" ").strip()
            if text:
                parts.append(f'<p><span id="{next_sid()}">{html_lib.escape(text)}</span></p>')

        return (
            "<!DOCTYPE html>\n<html>\n<head>\n"
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"<style>\n{_EPUB_RESPONSIVE_CSS}\n</style>\n"
            "</head>\n<body>\n"
            + "\n".join(parts)
            + "\n</body>\n</html>"
        )
