import re
import os
import json
import html as html_lib
import subprocess
import logging
import dataclasses
from collections import defaultdict
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from backend.app.services.page_image import save_page_image, sample_bg_color

logger = logging.getLogger(__name__)


def _figure_cleaning_enabled() -> bool:
    """Only auto-clean figures outside tests and when an API key exists."""
    return (not os.getenv("PYTEST_CURRENT_TEST")) and bool(os.getenv("GEMINI_API_KEY"))


def _banner_title_block(blocks: List[Dict[str, Any]], fb, page_w: float):
    """Return the title block overlaid on a banner figure, or None. A banner is a
    WIDE figure (spans >= _BANNER_MIN_WIDTH_FRAC of the page) holding at most
    _BANNER_MAX_BLOCKS text blocks, whose largest block is a real title (font size
    >= _BANNER_MIN_TITLE_SIZE). This excludes example images, icons and captions
    that merely overlap a small label. bbox format is [x0, y0, w, h]."""
    from backend.app.services.flow_model import (
        _BANNER_MAX_BLOCKS, _BANNER_MIN_WIDTH_FRAC, _BANNER_MIN_TITLE_SIZE,
    )
    fx, fy, fw, fh = fb
    if fw <= 0 or fh <= 0 or not page_w or fw < _BANNER_MIN_WIDTH_FRAC * page_w:
        return None
    contained = []
    for blk in blocks:
        bx, by, bw, bh = blk["bbox"]
        cx, cy = bx + bw / 2, by + bh / 2
        if fx <= cx <= fx + fw and fy <= cy <= fy + fh and fw * fh > bw * bh:
            contained.append(blk)
    if not contained or len(contained) > _BANNER_MAX_BLOCKS:
        return None

    def _fsize(b) -> float:
        return (b.get("font") or {}).get("size") or 0

    primary = max(contained, key=_fsize)
    return primary if _fsize(primary) >= _BANNER_MIN_TITLE_SIZE else None


_DOCLING_RESPONSIVE_CSS = """
* { box-sizing: border-box; }
body {
    font-family: Arial, sans-serif;
    line-height: 1.7;
    max-width: 800px;
    margin: 0 auto;
    padding: 1.5rem;
    color: #333;
}
h1, h2, h3, h4, h5, h6 {
    margin-top: 1.4em;
    margin-bottom: 0.4em;
    line-height: 1.3;
}
p { margin: 0.6em 0; }
ul, ol { padding-left: 1.6em; }
li { margin: 0.3em 0; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    overflow-x: auto;
    display: block;
}
th, td {
    border: 1px solid #ddd;
    padding: 8px 12px;
    text-align: left;
}
th { background: #f2f2f2; font-weight: bold; }
pre {
    background: #f6f8fa;
    padding: 1em;
    border-radius: 4px;
    overflow-x: auto;
}
code { font-family: monospace; font-size: 0.9em; }
figure { margin: 1.2em 0; text-align: center; }
img { max-width: 100%; height: auto; }
figcaption { color: #666; font-style: italic; font-size: 0.9em; }
"""

class Extractor:
    @staticmethod
    def sanitize_html(html_content: str) -> str:
        """
        Sanitizes raw absolute positioned HTML:
        1. Strips grey backgrounds (#A0A0A0) and replaces with white/neutral layouts.
        2. Injects UTF-8 meta charset tag in <head> to prevent encoding issues.
        3. Normalizes traditional pdftohtml v0.40 markup into Poppler absolute span format
           (assigns sequential span IDs and copies parent coordinates).
        """
        # Replace background colors
        sanitized = re.sub(r'#A0A0A0', '#FFFFFF', html_content, flags=re.IGNORECASE)
        
        # Inject meta charset if not present
        if "charset=utf-8" not in sanitized.lower() and "<head>" in sanitized.lower():
            utf8_meta = '<meta charset="utf-8">'
            sanitized = re.sub(
                r'(<head\b[^>]*>)', 
                r'\1\n<meta charset="utf-8">', 
                sanitized, 
                count=1, 
                flags=re.IGNORECASE
            )
            
        # Parse with BeautifulSoup to normalize HTML elements
        soup = BeautifulSoup(sanitized, "html.parser")
        spans = soup.find_all("span")
        
        # Track target absolute parent elements to clean later, preventing coordinate accumulation
        parents_to_clean = {}
        
        for idx, span in enumerate(spans):
            # 1. Assign unique sequential ID if missing
            if not span.get("id"):
                span["id"] = f"s{idx + 1}"
                
            # 2. Check if this span has no inline absolute layout coordinates
            style = span.get("style", "")
            has_left = "left:" in style.lower()
            has_top = "top:" in style.lower()
            
            if not (has_left and has_top):
                # We need to trace up to parent/grandparent <DIV> to find absolute positions
                parent = span.parent
                left_val, top_val = None, None
                target_parent = None
                
                # Walk up up to 3 levels to find the absolute positioned container
                for _ in range(3):
                    if not parent:
                        break
                    p_style = parent.get("style", "")
                    if "position:" in p_style.lower() or "left:" in p_style.lower() or "top:" in p_style.lower():
                        target_parent = parent
                        # Extract left and top from parent style
                        left_match = re.search(r'left:\s*([\d\.]+)px?', p_style, re.IGNORECASE)
                        top_match = re.search(r'top:\s*([\d\.]+)px?', p_style, re.IGNORECASE)
                        
                        # pdftohtml v0.40 might write top:99 (without px)
                        if not left_match:
                            left_match = re.search(r'left:\s*(\d+)', p_style, re.IGNORECASE)
                        if not top_match:
                            top_match = re.search(r'top:\s*(\d+)', p_style, re.IGNORECASE)
                            
                        if left_match:
                            left_val = float(left_match.group(1))
                        if top_match:
                            top_val = float(top_match.group(1))
                        break
                    parent = parent.parent
                    
                if left_val is not None and top_val is not None and target_parent is not None:
                    # Inject style properties directly into the span tag!
                    span["style"] = f"position:absolute; left:{left_val}px; top:{top_val}px;"
                    
                    # Store target parent for later style cleanup
                    parent_id = id(target_parent)
                    if parent_id not in parents_to_clean:
                        parents_to_clean[parent_id] = target_parent
                        
        # Now clean all marked parents style to prevent coordinate inheritance issues
        for parent_node in parents_to_clean.values():
            p_style = parent_node.get("style", "")
            p_style_cleaned = re.sub(r'position\s*:\s*absolute;?', '', p_style, flags=re.IGNORECASE)
            p_style_cleaned = re.sub(r'left\s*:\s*[^;]+;?', '', p_style_cleaned, flags=re.IGNORECASE)
            p_style_cleaned = re.sub(r'top\s*:\s*[^;]+;?', '', p_style_cleaned, flags=re.IGNORECASE)
            parent_node["style"] = p_style_cleaned.strip()
            
        return str(soup)

    @staticmethod
    def extract_spans(html_content: str) -> List[Dict[str, Any]]:
        """
        Extracts all span elements with their IDs and text.
        Coordinates (left, top) are included when present (pdftohtml output) but not required
        (Docling semantic output has no absolute positioning).
        """
        soup = BeautifulSoup(html_content, "html.parser")
        spans_data = []

        for span in soup.find_all("span"):
            span_id = span.get("id")
            if not span_id:
                continue

            text = span.get_text()
            if not text.strip():
                continue

            style = span.get("style", "")
            left_match = re.search(r'left:\s*([\d\.]+)px', style)
            top_match = re.search(r'top:\s*([\d\.]+)px', style)

            entry: Dict[str, Any] = {"id": span_id, "text": text}
            if left_match and top_match:
                entry["left"] = float(left_match.group(1))
                entry["top"] = float(top_match.group(1))

            spans_data.append(entry)

        return spans_data

    @staticmethod
    def extract_pdf_to_html_cli(pdf_path: str, output_dir: str, doc_id: str) -> List[str]:
        """
        Runs the pdftohtml CLI command to convert PDF into HTML pages.
        Supports both modern Poppler and traditional Sourceforge pdftohtml v0.40
        by dynamically splitting single massive outputs if needed.
        """
        os.makedirs(output_dir, exist_ok=True)
        output_prefix = os.path.join(output_dir, doc_id)
        
        # Build command: Use pdftohtml v0.40 compatible layout options (-c, -noframes) and force UTF-8 encoding
        cmd = ["pdftohtml", "-enc", "UTF-8", "-c", "-noframes", pdf_path, output_prefix]
        
        try:
            logger.info(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"pdftohtml CLI run successfully. stdout: {result.stdout}")
        except Exception as e:
            logger.error(f"Failed to run pdftohtml CLI: {e}")
            raise e
            
        # Detect if pdftohtml v0.40 generated a single massive HTML file instead of separate pages
        single_html_path = f"{output_prefix}.html"
        if os.path.exists(single_html_path):
            logger.info(f"pdftohtml v0.40 massive output detected at {single_html_path}. Splitting into separate pages...")
            
            with open(single_html_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                
            # Extract head/style declarations to copy to each subpage to maintain fonts and styles
            head_match = re.search(r"<head>(.*?)</head>", content, re.DOTALL | re.IGNORECASE)
            head_content = head_match.group(1) if head_match else ""
            
            # Split content by page anchors: <a name="1"></a> or <a name="2">
            pages_split = re.split(r'<a\s+name="(\d+)"\s*>\s*(?:</a>)?', content, flags=re.IGNORECASE)
            
            # pages_split pattern: [header_content, "1", page_1_body, "2", page_2_body, ...]
            i = 1
            while i < len(pages_split):
                page_num_str = pages_split[i]
                page_body = pages_split[i+1] if i + 1 < len(pages_split) else ""
                
                # Wrap page body in full html skeleton
                page_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{head_content}
</head>
<body bgcolor="#A0A0A0" vlink="blue" link="blue">
{page_body}
</body>
</html>"""
                
                page_file_path = os.path.normpath(os.path.join(output_dir, f"{doc_id}-{page_num_str}.html"))
                with open(page_file_path, "w", encoding="utf-8") as pf:
                    pf.write(page_html)
                
                i += 2
            
            logger.info("Successfully split massive html file into separate page files!")

        # Find generated page HTML files
        html_files = []
        for file in os.listdir(output_dir):
            # Check for pattern <doc_id>-<page_num>.html
            if file.startswith(f"{doc_id}-") and file.endswith(".html"):
                html_files.append(os.path.join(output_dir, file))
                
        # Sort them numerically based on the page number
        def get_page_num(path):
            filename = os.path.basename(path)
            try:
                num_str = filename[len(doc_id)+1 : -5]
                return int(num_str)
            except ValueError:
                return 9999
                
        html_files.sort(key=get_page_num)
        return html_files


class DoclingExtractor:
    """PDF extractor using IBM Docling for semantic, responsive HTML output."""

    _converter = None  # module-level singleton to avoid repeated model loading

    @classmethod
    def _get_converter(cls):
        if cls._converter is None:
            try:
                from docling.document_converter import DocumentConverter, PdfFormatOption
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import (
                    PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
                )
                pipeline_options = PdfPipelineOptions()
                pipeline_options.generate_page_images = True
                pipeline_options.images_scale = 2.0
                # Use CPU explicitly — MPS on Apple Silicon doesn't support float64
                pipeline_options.accelerator_options = AcceleratorOptions(
                    num_threads=4, device=AcceleratorDevice.CPU
                )
                cls._converter = DocumentConverter(
                    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
                )
                logger.info("DoclingExtractor: converter initialised (CPU mode)")
            except ImportError:
                raise RuntimeError("docling is not installed. Run: pip install docling")
        return cls._converter

    @classmethod
    def extract_pdf_to_html(cls, pdf_path: str, output_dir: str, doc_id: str) -> List[str]:
        """
        Convert a PDF to per-page semantic HTML files.
        Returns a list of file paths in page order — same interface as
        Extractor.extract_pdf_to_html_cli() so the router can use both interchangeably.
        """
        os.makedirs(output_dir, exist_ok=True)
        converter = cls._get_converter()

        logger.info(f"DoclingExtractor: converting {pdf_path}")
        result = converter.convert(Path(pdf_path))
        doc = result.document
        logger.info(f"DoclingExtractor: converted {len(doc.pages)} pages")

        # Group document items by page number
        pages_items: Dict[int, list] = defaultdict(list)
        for item, level in doc.iterate_items():
            if hasattr(item, "prov") and item.prov:
                pages_items[item.prov[0].page_no].append((item, level))

        html_files = []
        for page_no in sorted(pages_items.keys()):
            _pages_sorted = sorted(pages_items.keys())
            _total_pages = len(_pages_sorted)
            _page_index = _pages_sorted.index(page_no)
            page_item = doc.pages.get(page_no)
            page_size = page_item.size if page_item else None
            # Always derive docling figure boxes + a fallback text build.
            _docling_html, _docling_blocks, fig_boxes = cls._items_to_page_html(
                pages_items[page_no], page_no, page_size)

            # PyMuPDF is the primary text source (complete coverage). Build the
            # docling item list (label + bbox top-left points) for role tagging.
            from backend.app.services.pdf_text_extractor import extract_text_blocks
            from backend.app.services.semantic_tagger import tag_blocks
            from docling_core.types.doc import CoordOrigin

            _page_h_pt = getattr(page_size, "height", None)
            _docling_items = []
            if _page_h_pt is not None:
                for _item, _lvl in pages_items[page_no]:
                    _prov = getattr(_item, "prov", None)
                    if not _prov:
                        continue
                    _bb = _prov[0].bbox
                    _tl = _bb if _bb.coord_origin == CoordOrigin.TOPLEFT else _bb.to_top_left_origin(page_height=_page_h_pt)
                    _docling_items.append({
                        "label": str(getattr(_item, "label", "text")),
                        "bbox": [_tl.l, min(_tl.t, _tl.b), _tl.r - _tl.l, abs(_tl.b - _tl.t)],
                    })

            _pm_blocks = extract_text_blocks(str(pdf_path), page_no)
            if _pm_blocks:
                _tagged = tag_blocks(_pm_blocks, _docling_items)
                page_html, blocks = cls._blocks_to_page_html(_tagged, page_no)
            else:
                page_html, blocks = _docling_html, _docling_blocks

            file_path = os.path.normpath(os.path.join(output_dir, f"{doc_id}-{page_no}.html"))
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(page_html)
            html_files.append(file_path)

            # Render the page raster + build the positioned layout sidecar.
            # Guarded per-page: a raster failure degrades THIS page to flow HTML
            # (image=None, blocks=[]) without aborting the whole extraction run.
            image_name = None
            pil_img = getattr(page_item.image, "pil_image", None) if (page_item and page_item.image) else None
            if pil_img is not None and page_size is not None:
                try:
                    image_name = save_page_image(pil_img, output_dir, doc_id, page_no)
                    img_path = os.path.join(output_dir, image_name)
                    scale_x = pil_img.width / page_size.width
                    scale_y = pil_img.height / page_size.height
                    for blk in blocks:
                        l, t, w, h = blk["bbox"]
                        bbox_px = (l * scale_x, t * scale_y, (l + w) * scale_x, (t + h) * scale_y)
                        blk["bg"] = sample_bg_color(img_path, bbox_px)
                except Exception as raster_err:
                    logger.warning(f"Page {page_no} raster failed, degrading to flow HTML: {raster_err}")
                    image_name = None

            layout = {
                "page_w": page_size.width if page_size else None,
                "page_h": page_size.height if page_size else None,
                "image": image_name,
                "blocks": blocks if image_name else [],
            }
            layout_path = os.path.normpath(os.path.join(output_dir, f"{doc_id}-{page_no}.layout.json"))
            with open(layout_path, "w", encoding="utf-8") as f:
                def _dc_default(o):
                    if dataclasses.is_dataclass(o) and not isinstance(o, type):
                        return dataclasses.asdict(o)
                    raise TypeError(f"Not serializable: {type(o)}")
                json.dump(layout, f, default=_dc_default)

            # ── PageModel (SP-A): typography + figures + classification ──
            from backend.app.services.page_model import PageModel, Block, Figure
            from backend.app.services.typography_extractor import extract_page_fonts
            from backend.app.services.figure_extractor import crop_figure
            from backend.app.services.page_classifier import classify_kind

            # PyMuPDF path already carries per-block font; only run the
            # bbox-matching font extractor for the docling fallback path.
            fonts = {}
            if blocks and not blocks[0].get("font"):
                try:
                    fonts = extract_page_fonts(str(pdf_path), page_no, blocks)
                except Exception as e:
                    logger.warning(f"Font extraction failed p{page_no}: {e}")

            figures = []
            if pil_img is not None and page_size is not None and fig_boxes:
                sx = pil_img.width / page_size.width
                sy = pil_img.height / page_size.height
                for i, fb in enumerate(fig_boxes, start=1):
                    try:
                        fname = crop_figure(pil_img, fb, sx, sy, output_dir, doc_id, page_no, i)
                        _fig = Figure(bbox=fb, img=fname)
                        # Only AI-clean genuine banners (wide figure + overlaid
                        # title), and only the TITLE REGION via inpaint+verify — never
                        # whole-clean a figure (that destroys content like faces). The
                        # title block's box is mapped to the cropped figure's pixels so
                        # the rest of the banner stays pixel-identical.
                        title = _banner_title_block(blocks, fb, page_size.width)
                        if title is not None and _figure_cleaning_enabled():
                            try:
                                from PIL import Image as _PILImage
                                from backend.app.services.image_cleaner import (
                                    clean_banner_inpaint_verified,
                                )
                                _cp = os.path.join(output_dir, fname)
                                fw_px, fh_px = _PILImage.open(_cp).size
                                fx, fy, fw, fh = fb
                                tb = title["bbox"]
                                sxp, syp = fw_px / fw, fh_px / fh
                                box_px = ((tb[0] - fx) * sxp, (tb[1] - fy) * syp,
                                          tb[2] * sxp, tb[3] * syp)
                                _cn = fname.rsplit(".", 1)[0] + ".clean.png"
                                if clean_banner_inpaint_verified(
                                        _cp, os.path.join(output_dir, _cn), [box_px]):
                                    _fig.clean_img = _cn
                            except Exception as _e:
                                logger.warning(f"Banner clean failed p{page_no} #{i}: {_e}")
                        figures.append(_fig)
                    except Exception as e:
                        logger.warning(f"Figure crop failed p{page_no} #{i}: {e}")

            # Merge clusters of adjacent figures (a PDF split image, or a row of
            # images) back into a single faithful crop — restores row layout and
            # baked captions. Skipped when unrelated body text sits in the region.
            if pil_img is not None and page_size is not None and len(figures) >= 2:
                try:
                    from backend.app.services.figure_grouper import (
                        plan_merge_groups, crop_group_region)
                    _figbb = [list(f.bbox) for f in figures]
                    _blkbb = [list(b["bbox"]) for b in blocks]
                    _plans = plan_merge_groups(_figbb, _blkbb,
                                               page_size.width, page_size.height)
                    if _plans:
                        _merged_idx: set = set()
                        _new: list = []
                        for _gi, _plan in enumerate(_plans, start=1):
                            _merged_idx.update(_plan["members"])
                            _gname = f"{doc_id}-{page_no}-figgroup{_gi}.png"
                            _crop = crop_group_region(
                                pil_img, _plan["bbox"], page_size.width, page_size.height)
                            _crop.save(os.path.join(output_dir, _gname))
                            _new.append(Figure(bbox=_plan["bbox"], img=_gname,
                                               kind="illustration"))
                        figures = [f for _k, f in enumerate(figures)
                                   if _k not in _merged_idx] + _new
                except Exception as _e:
                    logger.warning(f"Figure grouping failed p{page_no}: {_e}")

            # ── Faithful figures: per-figure alignment + composite design-region
            # crop (chat-like icon+text bands → one image, kept centered). ──
            if page_size is not None:
                from backend.app.services.design_region import (
                    infer_figure_align, detect_design_regions)
                for _f in figures:
                    _f.align = infer_figure_align(list(_f.bbox), page_size.width)
                if pil_img is not None and figures:
                    try:
                        from backend.app.services.figure_grouper import crop_group_region
                        _figbb = [list(f.bbox) for f in figures]
                        _blk = [(b["span_id"], list(b["bbox"])) for b in blocks]
                        _regs = detect_design_regions(
                            _figbb, _blk, page_size.width, page_size.height)
                        if _regs:
                            _rm_fig: set = set()
                            _rm_blk: set = set()
                            _newr: list = []
                            for _ri, _rg in enumerate(_regs, start=1):
                                _rm_fig.update(_rg.figure_idx)
                                _rm_blk.update(_rg.block_ids)
                                _rname = f"{doc_id}-{page_no}-region{_ri}.png"
                                crop_group_region(
                                    pil_img, _rg.bbox,
                                    page_size.width, page_size.height
                                ).save(os.path.join(output_dir, _rname))
                                _newr.append(Figure(bbox=_rg.bbox, img=_rname,
                                                    kind="content-region", align="center"))
                            figures = [f for _k, f in enumerate(figures)
                                       if _k not in _rm_fig] + _newr
                            blocks = [b for b in blocks
                                      if b["span_id"] not in _rm_blk]
                    except Exception as _e:
                        logger.warning(f"Design-region crop failed p{page_no}: {_e}")

            boxes = {}
            if image_name and pil_img is not None and page_size is not None:
                from backend.app.services.page_image import analyze_block_box
                _bsx = pil_img.width / page_size.width
                _bsy = pil_img.height / page_size.height
                _img_path = os.path.join(output_dir, image_name)
                for b in blocks:
                    try:
                        boxes[b["span_id"]] = analyze_block_box(_img_path, b["bbox"], _bsx, _bsy)
                    except Exception as e:
                        logger.warning(f"analyze_block_box failed p{page_no} {b['span_id']}: {e}")

            model_blocks = [
                Block(span_id=b["span_id"], role=b.get("role", "body"), bbox=b["bbox"],
                      text="", font=b.get("font") or fonts.get(b["span_id"]),
                      box=boxes.get(b["span_id"]))
                for b in blocks
            ]
            pw = page_size.width if page_size else 1.0
            ph = page_size.height if page_size else 1.0
            bg_is_photo = False
            if image_name and pil_img is not None and page_size is not None:
                from backend.app.services.page_image import is_photo_background
                _sx = pil_img.width / page_size.width
                _sy = pil_img.height / page_size.height
                bg_is_photo = is_photo_background(
                    os.path.join(output_dir, image_name), pw, ph,
                    [b["bbox"] for b in blocks], [f.bbox for f in figures], _sx, _sy)
            kind = classify_kind(pw, ph, [b["bbox"] for b in blocks],
                                 [f.bbox for f in figures], bg_is_photo=bg_is_photo)
            bg_color = blocks[0].get("bg", "#ffffff") if blocks else "#ffffff"

            # ── #0 eligibility: per-figure photo/diagram → page_class + cover ──
            from backend.app.services.picture_classifier import classify_picture_file
            from backend.app.services.page_eligibility import classify_page, detect_cover
            figure_labels = []
            for _fig in figures:
                try:
                    figure_labels.append(
                        classify_picture_file(os.path.join(output_dir, _fig.img))[0])
                except Exception as _e:
                    logger.warning(f"picture classify failed p{page_no} {_fig.img}: {_e}")
                    figure_labels.append("uncertain")   # safe → preserve
            _page_area = max(pw * ph, 1.0)
            _text_ratio = sum(b["bbox"][2] * b["bbox"][3] for b in blocks) / _page_area
            _fig_ratio = sum(f.bbox[2] * f.bbox[3] for f in figures) / _page_area
            _has_table = any(b.get("role") == "table" for b in blocks)
            page_class = classify_page(_text_ratio, _fig_ratio, figure_labels,
                                       has_table=_has_table, bg_is_photo=bg_is_photo)
            cover = detect_cover(_page_index, _total_pages, text_ratio=_text_ratio,
                                 fig_ratio=_fig_ratio, bg_is_photo=bg_is_photo)

            model = PageModel(
                page_w=pw, page_h=ph, kind=kind,
                background={"color": bg_color,
                            "image": image_name if kind != "text" else None},
                blocks=model_blocks, figures=figures,
                page_class=page_class, cover=cover,
            )
            model_path = os.path.normpath(os.path.join(output_dir, f"{doc_id}-{page_no}.model.json"))
            with open(model_path, "w", encoding="utf-8") as f:
                f.write(model.to_json())

        return html_files

    @staticmethod
    def _items_to_page_html(items: list, page_no: int, page_size=None):
        """
        Render (DocItem, level) pairs as a self-contained HTML page AND return a
        parallel list of positioned text blocks {span_id, bbox:[l,t,w,h] top-left
        points} so the overlay renderer can place translated text over the raster.
        """
        from docling_core.types.doc import CoordOrigin

        span_counter = [0]
        blocks: List[dict] = []
        figures: List[list] = []
        page_h = getattr(page_size, "height", None)

        def record_block(sid: str, item) -> None:
            prov = getattr(item, "prov", None)
            if not prov or page_h is None:
                return
            bb = prov[0].bbox
            tl = bb if bb.coord_origin == CoordOrigin.TOPLEFT else bb.to_top_left_origin(page_height=page_h)
            # to_top_left_origin gives tl.t < tl.b for valid boxes; use min()/abs()
            # defensively so an unexpected coord ordering can't yield a negative height.
            top = min(tl.t, tl.b)
            blocks.append({"span_id": sid, "bbox": [tl.l, top, tl.r - tl.l, abs(tl.b - tl.t)]})

        def wrap(text: str, item=None) -> str:
            span_counter[0] += 1
            sid = f"s{span_counter[0]}"
            if item is not None:
                record_block(sid, item)
            return f'<span id="{sid}">{html_lib.escape(text)}</span>'

        body_parts: List[str] = []
        open_list = False

        for item, level in items:
            text: str = getattr(item, "text", "") or ""
            label: str = str(getattr(item, "label", "text"))

            if label == "list_item":
                if not open_list:
                    body_parts.append("<ul>")
                    open_list = True
                body_parts.append(f"  <li>{wrap(text, item)}</li>")
                continue

            if open_list:
                body_parts.append("</ul>")
                open_list = False

            if not text and label not in ("picture",):
                continue

            if label == "section_header":
                h = min(max(level + 1, 2), 6)
                body_parts.append(f"<h{h}>{wrap(text, item)}</h{h}>")
            elif label == "code":
                body_parts.append(f"<pre><code>{html_lib.escape(text)}</code></pre>")
            elif label == "picture":
                prov = getattr(item, "prov", None)
                if prov and page_h is not None:
                    from docling_core.types.doc import CoordOrigin
                    bb = prov[0].bbox
                    tl = bb if bb.coord_origin == CoordOrigin.TOPLEFT else bb.to_top_left_origin(page_height=page_h)
                    figures.append([tl.l, min(tl.t, tl.b), tl.r - tl.l, abs(tl.b - tl.t)])
                body_parts.append(f'<figure><img src="" alt="Figure on page {page_no}"/></figure>')
            elif label == "table":
                body_parts.append(DoclingExtractor._table_text_to_html(text))
            else:
                body_parts.append(f"<p>{wrap(text, item)}</p>")

        if open_list:
            body_parts.append("</ul>")

        html = (
            f"<!DOCTYPE html>\n<html>\n<head>\n"
            f'<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"<style>\n{_DOCLING_RESPONSIVE_CSS}\n</style>\n"
            f"</head>\n<body>\n"
            + "\n".join(body_parts)
            + "\n</body>\n</html>"
        )
        return html, blocks, figures

    @staticmethod
    def _blocks_to_page_html(tagged_blocks, page_no):
        """Build semantic HTML + a parallel block list from PyMuPDF tagged blocks.
        Mirrors _items_to_page_html's output shape but sourced from PyMuPDF:
        each returned block carries span_id, bbox, font (FontSpec), role."""
        parts = []
        blocks = []
        open_list = False
        for i, b in enumerate(tagged_blocks, start=1):
            sid = f"s{i}"
            blocks.append({"span_id": sid, "bbox": b["bbox"],
                           "font": b.get("font"), "role": b.get("role", "body")})
            span = f'<span id="{sid}">{html_lib.escape(b["text"])}</span>'
            role = b.get("role", "body")
            if role == "list":
                if not open_list:
                    parts.append("<ul>")
                    open_list = True
                parts.append(f"<li>{span}</li>")
                continue
            if open_list:
                parts.append("</ul>")
                open_list = False
            if role == "heading":
                parts.append(f"<h2>{span}</h2>")
            else:
                parts.append(f"<p>{span}</p>")
        if open_list:
            parts.append("</ul>")
        html = (
            f"<!DOCTYPE html>\n<html>\n<head>\n"
            f'<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"<style>\n{_DOCLING_RESPONSIVE_CSS}\n</style>\n"
            f"</head>\n<body>\n"
            + "\n".join(parts)
            + "\n</body>\n</html>"
        )
        return html, blocks

    @staticmethod
    def _table_text_to_html(text: str) -> str:
        """
        Convert tab-delimited table text (from Docling) to a semantic HTML table.
        First row becomes <th> header cells; remaining rows become <td> data cells.
        Falls back to <pre> when the text has no tab structure.
        """
        lines = [line for line in text.strip().splitlines() if line.strip()]
        if not lines or "\t" not in lines[0]:
            return f"<pre>{html_lib.escape(text)}</pre>"

        rows = [line.split("\t") for line in lines]
        header = rows[0]
        body_rows = rows[1:]

        ths = "".join(f"<th>{html_lib.escape(cell.strip())}</th>" for cell in header)
        trs = "".join(
            "<tr>"
            + "".join(f"<td>{html_lib.escape(cell.strip())}</td>" for cell in row)
            + "</tr>"
            for row in body_rows
        )
        return f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>"
