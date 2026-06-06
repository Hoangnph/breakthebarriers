"""Render a list of FlowElements as a single scrolling semantic HTML document."""
from __future__ import annotations
import html as html_lib
from typing import List

from backend.app.services.flow_model import FlowElement
from backend.app.services.toc_parser import parse_toc_entry

_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Be+Vietnam+Pro:wght@400;700&amp;display=swap" rel="stylesheet">'
)
_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #f4f4f5; font-family: 'Be Vietnam Pro', system-ui, sans-serif; }
.fl-doc { max-width: 720px; margin: 0 auto; padding: 48px 24px 120px;
          background: #fff; color: #1a1a1a; line-height: 1.7; }
.fl-doc h1 { font-size: 2rem; margin: 1.6em 0 .5em; line-height: 1.25; }
.fl-doc h2 { font-size: 1.5rem; margin: 1.4em 0 .5em; }
.fl-doc h3 { font-size: 1.2rem; margin: 1.2em 0 .5em; }
.fl-doc p { margin: 0 0 1em; }
.fl-doc p.cap { font-size: .9rem; color: #666; }
.fl-doc p.li { padding-left: 1.25em; text-indent: -1.1em; }
.fl-doc figure { margin: 1.5em 0; }
.fl-fig { max-width: 100%; height: auto; display: block; }
.fl-page { width: 100%; height: auto; display: block; margin: 1.5em 0;
           border-radius: 4px; }
.fl-doc section { scroll-margin-top: 16px; }
.fl-contents { margin: 1.5em 0; padding: 0; }
.fl-toc-link { display: flex; align-items: flex-end; text-decoration: none;
               color: inherit; margin: .25em 0; }
.fl-toc-link .t { flex: 0 1 auto; }
.fl-toc-dots { flex: 1 1 8px; min-width: 8px; margin: 0 4px 4px;
               border-bottom: 1px dotted #aaa; }
.fl-toc-link.lvl2 { margin-left: 1.5em; }
.fl-toc-link.lvl3 { margin-left: 3em; }
.fl-toc-link:hover .t { text-decoration: underline; }
"""


def _clamp_level(level: int) -> int:
    return level if level in (1, 2, 3) else 3


def _heading_entries(flow: List[FlowElement], translations: dict | None) -> list:
    out = []
    for el in flow:
        if el.kind == "heading":
            text = (translations or {}).get(el.span_id)
            if text:
                out.append((el.span_id, el.level, text))
    return out


def _contents_html(headings: list) -> str:
    links = []
    for span, level, text in headings:
        lvl = _clamp_level(level)
        sid = html_lib.escape(f"sec-{span}", quote=True)
        links.append(
            f'<a href="#{sid}" class="fl-toc-link lvl{lvl}">'
            f'<span class="t">{html_lib.escape(text)}</span>'
            f'<span class="fl-toc-dots"></span></a>')
    return f'<nav class="fl-contents">{"".join(links)}</nav>'


def render_flow_html(flow: List[FlowElement], translations: dict,
                     image_url_base: str) -> str:
    headings = _heading_entries(flow, translations)
    contents_html = _contents_html(headings) if headings else ""
    parts: List[str] = []
    section_open = False
    contents_done = False

    def ensure_section():
        nonlocal section_open
        if not section_open:
            parts.append('<section class="fl-intro">')
            section_open = True

    for el in flow:
        text = (translations or {}).get(el.span_id) if el.span_id else None
        if el.kind in ("paragraph", "caption", "list") and text and parse_toc_entry(text):
            if not contents_done and contents_html:
                ensure_section()
                parts.append(contents_html)
                contents_done = True
                continue
            if contents_done:
                continue          # already placed nav; suppress remaining TOC entries
            # else: no headings → no nav; fall through and render the text normally
        if el.kind == "heading" and text:
            if section_open:
                parts.append("</section>")
            sid = html_lib.escape(f"sec-{el.span_id}", quote=True)
            parts.append(f'<section id="{sid}">')
            section_open = True
            lvl = _clamp_level(el.level)
            span = html_lib.escape(el.span_id or "", quote=True)
            parts.append(f'<h{lvl} data-span="{span}">{html_lib.escape(text)}</h{lvl}>')
            continue
        if el.kind == "image_block" and el.src:
            ensure_section()
            src = html_lib.escape(f"{image_url_base}/{el.src}", quote=True)
            parts.append(f'<img class="fl-page" src="{src}" alt="page"/>')
            continue
        if el.kind == "figure" and el.src:
            ensure_section()
            src = html_lib.escape(f"{image_url_base}/{el.src}", quote=True)
            parts.append(f'<figure><img class="fl-fig" src="{src}" alt="figure"/></figure>')
            continue
        if not text:
            continue
        ensure_section()
        span = html_lib.escape(el.span_id or "", quote=True)
        body = html_lib.escape(text)
        if el.kind == "caption":
            parts.append(f'<p class="cap" data-span="{span}">{body}</p>')
        elif el.kind == "list":
            parts.append(f'<p class="li" data-span="{span}">• {body}</p>')
        else:
            parts.append(f'<p data-span="{span}">{body}</p>')
    if section_open:
        parts.append("</section>")
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'{_FONTS}<style>{_CSS}</style></head><body>'
        f'<article class="fl-doc">{"".join(parts)}</article></body></html>'
    )
