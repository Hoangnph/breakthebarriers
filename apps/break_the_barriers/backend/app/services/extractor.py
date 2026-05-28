import re
import os
import subprocess
import logging
from bs4 import BeautifulSoup
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

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
        Extracts all span elements with their IDs, text, and parsed coordinates (left, top).
        """
        soup = BeautifulSoup(html_content, "html.parser")
        spans_data = []
        
        for span in soup.find_all("span"):
            span_id = span.get("id")
            if not span_id:
                continue
                
            text = span.get_text()
            style = span.get("style", "")
            
            # Parse absolute coordinates using regex
            left_match = re.search(r'left:\s*([\d\.]+)px', style)
            top_match = re.search(r'top:\s*([\d\.]+)px', style)
            
            if left_match and top_match:
                left = float(left_match.group(1))
                top = float(top_match.group(1))
                
                spans_data.append({
                    "id": span_id,
                    "text": text,
                    "top": top,
                    "left": left
                })
                
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
