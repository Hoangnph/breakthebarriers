"""Render a list of FlowElements as a single scrolling semantic HTML document."""
from __future__ import annotations
import html as html_lib
from typing import List

from backend.app.services.flow_model import FlowElement

_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Be+Vietnam+Pro:wght@400;700&display=swap" rel="stylesheet">'
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
.fl-doc figure { margin: 1.5em 0; }
.fl-fig { max-width: 100%; height: auto; display: block; }
.fl-page { width: 100%; height: auto; display: block; margin: 1.5em 0;
           border-radius: 4px; }
"""


def render_flow_html(flow: List[FlowElement], translations: dict,
                     image_url_base: str) -> str:
    parts: List[str] = []
    for el in flow:
        if el.kind == "image_block" and el.src:
            src = html_lib.escape(f"{image_url_base}/{el.src}", quote=True)
            parts.append(f'<img class="fl-page" src="{src}" alt="page"/>')
            continue
        if el.kind == "figure" and el.src:
            src = html_lib.escape(f"{image_url_base}/{el.src}", quote=True)
            parts.append(f'<figure><img class="fl-fig" src="{src}" alt="figure"/></figure>')
            continue
        text = (translations or {}).get(el.span_id)
        if not text:
            continue
        span = html_lib.escape(el.span_id or "", quote=True)
        body = html_lib.escape(text)
        if el.kind == "heading":
            lvl = el.level if el.level in (1, 2, 3) else 3
            parts.append(f'<h{lvl} data-span="{span}">{body}</h{lvl}>')
        elif el.kind == "caption":
            parts.append(f'<p class="cap" data-span="{span}">{body}</p>')
        elif el.kind == "list":
            parts.append(f'<p class="li" data-span="{span}">• {body}</p>')
        else:
            parts.append(f'<p data-span="{span}">{body}</p>')
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'{_FONTS}<style>{_CSS}</style></head><body>'
        f'<article class="fl-doc">{"".join(parts)}</article></body></html>'
    )
