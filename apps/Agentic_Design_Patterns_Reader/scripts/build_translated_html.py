import os
import json
import re

APP_DIR = "/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/Agentic_Design_Patterns_Reader"
PAGES_DIR = os.path.join(APP_DIR, "data", "pages")
PAGES_VI_DIR = os.path.join(APP_DIR, "data", "pages_vi")
LOCALE_VI_DIR = os.path.join(APP_DIR, "data", "locales", "vi")

os.makedirs(PAGES_VI_DIR, exist_ok=True)

for i in range(1, 483):
    html_path = os.path.join(PAGES_DIR, f"Agentic_Design_Patterns-{i}.html")
    json_path = os.path.join(LOCALE_VI_DIR, f"page_{i}.json")
    
    if not os.path.exists(html_path):
        continue
        
    output_html_path = os.path.join(PAGES_VI_DIR, f"Agentic_Design_Patterns-{i}.html")
    
    with open(html_path, 'r', encoding='ISO-8859-1') as f:
        html_content = f.read()
    
    # Fix the gray background of pdftohtml output (makes extra padding pure white instead of ugly gray)
    html_content = re.sub(r'bgcolor="#A0A0A0"', 'bgcolor="#FFFFFF"', html_content, flags=re.IGNORECASE)

    # Fix the charset from ISO-8859-1 to utf-8 so browser renders accented Vietnamese correctly
    html_content = re.sub(r'charset=ISO-8859-1', 'charset=utf-8', html_content, flags=re.IGNORECASE)

    if not os.path.exists(json_path):
        # Still write the html_content because we want the bgcolor fix applied everywhere!
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        continue
        
    with open(json_path, 'r', encoding='utf-8') as f:
        translations = json.load(f)
        
    class SpanReplacer:
        def __init__(self, translations):
            self.idx = 0
            self.translations = translations
            
        def __call__(self, match):
            idx_str = str(self.idx)
            self.idx += 1
            
            opening_tag = match.group(1)
            closing_tag = match.group(3)
            
            if idx_str in self.translations:
                return f"{opening_tag}{self.translations[idx_str]}{closing_tag}"
            else:
                return match.group(0)

    replacer = SpanReplacer(translations)
    # Use non-greedy match for span content
    new_html_content = re.sub(r'(<span[^>]*>)(.*?)(</span>)', replacer, html_content, flags=re.IGNORECASE | re.DOTALL)
    
    with open(output_html_path, 'w', encoding='utf-8') as f:
        f.write(new_html_content)

print("Built translated HTML pages using regex (preserved layout and fixed background colors).")
