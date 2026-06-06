"""Parse table-of-contents entries ("Title ..... 12") and detect TOC pages.

Pure, language-neutral: relies on a leader run (3+ dots, ellipsis chars, or a
tab) followed by a trailing page number — specific enough to avoid matching an
ordinary sentence that merely ends in a number."""
from __future__ import annotations
import re

_TOC_RE = re.compile(
    r'^(?P<title>.*?)\s*(?:\.{3,}|…+|\t)[\s.…]*(?P<num>\d+)\s*$')


def parse_toc_entry(text: str):
    """Return (title, page_num) for a TOC line, else None."""
    if not text:
        return None
    m = _TOC_RE.match(text)
    if not m:
        return None
    title = m.group("title").strip()
    if not title:
        return None
    return (title, m.group("num"))


def is_toc_page(block_texts, *, min_entries: int = 3) -> bool:
    """True when at least `min_entries` of the block texts parse as TOC lines."""
    return sum(1 for t in block_texts if parse_toc_entry(t)) >= min_entries
