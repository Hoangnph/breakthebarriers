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


_TOC_LOOSE_RE = re.compile(
    r'^(?P<title>.*?\S)\s*(?:\.{2,}|…+|\t|\s{2,})\s*(?P<num>\d+)\s*$')

# One "Title <dotted/ellipsis/tab leader> number" segment. Used with finditer so a
# single block that merged several TOC lines splits into one entry per line. The
# title excludes dot/ellipsis/tab so a match cannot swallow the next entry's leader.
_TOC_SEGMENT_RE = re.compile(
    r'(?P<title>[^\t.…]*?[^\t.…\d\s])\s*(?:\.{2,}|…+|\t)\s*(?P<num>\d{1,4})')


def extract_toc_entries(block_texts):
    """Ordered (title, page_num) entries from a TOC page's block texts. Looser than
    parse_toc_entry — safe because callers only use it on a confirmed TOC page
    (is_toc_page). A block that merged several TOC lines (dotted leaders) is split
    into one entry per line; a single-line block whose leader is just spaces falls
    back to the whole-line match."""
    out = []
    for t in block_texts:
        if not t:
            continue
        found = False
        for m in _TOC_SEGMENT_RE.finditer(t):
            title = m.group("title").strip(" .…\t")
            if title:
                out.append((title, m.group("num")))
                found = True
        if not found:
            m = _TOC_LOOSE_RE.match(t)
            if m:
                title = m.group("title").strip(" .…\t")
                if title:
                    out.append((title, m.group("num")))
    return out


def _norm_title(s):
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


def map_entry_to_page(title, page_headings, printed_num=None):
    """Map a TOC title to a raster page_num by matching against page headings
    (normalized equality / two-way prefix). Fallback: the printed number. Else None.
    page_headings: list[(page_num, heading_text)]."""
    nt = _norm_title(title)
    if nt:
        for pnum, htext in page_headings:
            nh = _norm_title(htext)
            if nh and (nh == nt or nh.startswith(nt) or nt.startswith(nh)):
                return pnum
    if printed_num is not None:
        try:
            return int(printed_num)
        except (TypeError, ValueError):
            return None
    return None
