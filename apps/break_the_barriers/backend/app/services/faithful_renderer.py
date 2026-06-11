"""Ráp HTML view Gốc: visual nền trung thực (SVG inline hoặc <img>) + lớp <span>
trong suốt định vị theo bbox để bôi đen/copy. Container có style width/height (px)
để script page_size của documents.py đọc được kích thước trang."""
import html as html_lib
from typing import Dict, Any

_FAITHFUL_CSS = """
*{box-sizing:border-box} body{margin:0;background:#fff}
.ff-page{position:relative;margin:0 auto}
.ff-page > svg,.ff-page > img{position:absolute;inset:0;width:100%;height:100%;display:block}
.ff-tl{position:absolute;color:transparent;white-space:pre;transform-origin:0 0;user-select:text}
"""


def render_faithful_page(visual: str, visual_kind: str, text_layer: Dict[str, Any],
                         page_w: float, page_h: float, asset_base: str = "") -> str:
    if visual_kind == "svg":
        base = visual
    else:
        src = f"{asset_base}/{visual}" if asset_base else visual
        base = f'<img src="{html_lib.escape(src, quote=True)}" alt=""/>'

    spans = []
    for s in text_layer.get("spans", []):
        x, y, w, h = s["bbox"]
        spans.append(
            f'<span class="ff-tl" style="left:{x:.2f}px;top:{y:.2f}px">'
            f'{html_lib.escape(s["text"])}</span>')

    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"<style>\n{_FAITHFUL_CSS}\n</style>\n</head>\n<body>\n"
        f'<div class="ff-page" style="width:{page_w:.0f}px;height:{page_h:.0f}px">\n'
        f"{base}\n" + "\n".join(spans) +
        "\n</div>\n</body>\n</html>")
