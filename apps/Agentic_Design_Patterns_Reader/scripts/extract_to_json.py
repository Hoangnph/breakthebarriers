import os
import json
import re
from bs4 import BeautifulSoup

# Define paths
APP_DIR = "/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/Agentic_Design_Patterns_Reader"
PAGES_DIR = os.path.join(APP_DIR, "data", "pages")
LOCALE_EN_DIR = os.path.join(APP_DIR, "data", "locales", "en")

os.makedirs(LOCALE_EN_DIR, exist_ok=True)

for i in range(1, 483):
    html_path = os.path.join(PAGES_DIR, f"Agentic_Design_Patterns-{i}.html")
    if not os.path.exists(html_path):
        continue
        
    with open(html_path, 'r', encoding='ISO-8859-1') as f:
        html_content = f.read()
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract text from all span elements (which are the leaf text nodes in pdftohtml)
    spans = soup.find_all('span')
    
    texts = {}
    for idx, span in enumerate(spans):
        text = span.get_text(strip=False)
        # Only save if it has actual letters (ignore purely empty spaces or single punctuation if you want, 
        # but better to save everything to maintain exact 1:1 mapping by index)
        texts[str(idx)] = text

    json_path = os.path.join(LOCALE_EN_DIR, f"page_{i}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(texts, f, ensure_ascii=False, indent=2)
        
print("Extracted English JSON for pages 1 to 20.")
