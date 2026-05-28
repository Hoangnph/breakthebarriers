from bs4 import BeautifulSoup
from typing import Dict

class Compiler:
    @staticmethod
    def inject_translation(original_html: str, translated_texts: Dict[str, str]) -> str:
        """
        Parses original absolute HTML, replaces text inside <span> elements with their
        corresponding translated values, and injects the Dynamic Font Shrink client script.
        """
        soup = BeautifulSoup(original_html, "html.parser")
        
        # Replace span text
        for span in soup.find_all("span"):
            span_id = span.get("id")
            if span_id and span_id in translated_texts:
                span.string = translated_texts[span_id]
                
        # String representation of compiled HTML
        compiled_html = str(soup)
        
        # Inject client-side Dynamic Font Shrink script to prevent text overflow
        shrink_script = """
<script>
window.addEventListener('load', function() {
    // Dynamic Font Shrink Auto-Recovery Script
    const pageWidthLimit = 1188; // Spec absolute canvas width limit
    const pageContainer = document.getElementById('page-container') || document.body;
    
    function performDynamicFontShrink() {
        const absoluteSpans = document.querySelectorAll('span[style*="left"]');
        let maximumRightCoordinate = 0;
        
        absoluteSpans.forEach(span => {
            const rect = span.getBoundingClientRect();
            const leftCoord = parseFloat(span.style.left) || 0;
            const approxWidth = span.textContent.length * 8; // Bounding box approximation
            const rightCoord = leftCoord + approxWidth;
            
            if (rightCoord > maximumRightCoordinate) {
                maximumRightCoordinate = rightCoord;
            }
        });
        
        if (maximumRightCoordinate > pageWidthLimit) {
            const ratio = pageWidthLimit / maximumRightCoordinate;
            const shrinkFactor = Math.max(0.75, Math.min(1.0, ratio));
            console.log(`[Safeguard] Page boundary overflow detected (${maximumRightCoordinate}px). Shrinking fonts by ${shrinkFactor}`);
            document.body.style.fontSize = `${shrinkFactor * 100}%`;
        }
    }
    
    performDynamicFontShrink();
});
</script>
"""
        # Inject before </body>
        if "</body>" in compiled_html:
            compiled_html = compiled_html.replace("</body>", f"{shrink_script}</body>")
        else:
            compiled_html += shrink_script
            
        return compiled_html

    @staticmethod
    def verify_quality_gates(original_html: str, translated_texts: Dict[str, str]) -> bool:
        """
        Quality Gate 2 (DOM Integrity Gate):
        Verifies that every span element with an ID has a corresponding translation.
        Returns False if any translated element is missing (preventing corrupted static output).
        """
        soup = BeautifulSoup(original_html, "html.parser")
        original_spans = soup.find_all("span")
        
        for span in original_spans:
            span_id = span.get("id")
            if span_id and span_id not in translated_texts:
                return False
                
        return True
