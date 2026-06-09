"""Render a document as a faithful vertical stack of its original page rasters.

The truth layer: each page is shown as its high-fidelity raster page-{n}.png, so the
rendered document is pixel-faithful to the source for ANY document (tables, vector
graphics, multi-column design, banners are all preserved because they ARE the raster).
Translation overlay is a later sub-project (B2); this renders the original pages.
Pure: page numbers + asset base URL in, one HTML document out."""
from __future__ import annotations
import html as html_lib
from typing import List

_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #f4f4f5; }
.fr-doc { max-width: 900px; margin: 0 auto; padding: 16px 12px 80px; }
.fr-page { margin: 0 0 16px; }
.fr-img { width: 100%; height: auto; display: block;
          box-shadow: 0 2px 14px rgba(0,0,0,.25); border-radius: 2px; }
"""

_ZOOM_SCRIPT = (
    "<script>window.addEventListener('message',function(e){"
    "var d=e.data||{};"
    "if(d.type==='btb-zoom'&&typeof d.zoom==='number'){"
    "var el=document.querySelector('.fr-doc');"
    "if(el)el.style.maxWidth=Math.max(200,900*d.zoom)+'px';}"
    "});</script>"
)


def render_faithful_flow(page_nums: List[int], image_url_base: str) -> str:
    base = html_lib.escape(image_url_base, quote=True)
    parts = []
    for n in sorted(int(x) for x in page_nums):
        parts.append(
            f'<figure id="pg-{n}" class="fr-page">'
            f'<img class="fr-img" src="{base}/page-{n}.png" '
            f'alt="Trang {n}" loading="lazy"/></figure>'
        )
    return (
        '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'<style>{_CSS}</style></head><body>'
        f'<article class="fr-doc">{"".join(parts)}</article>'
        f'{_ZOOM_SCRIPT}</body></html>'
    )
