import os
import json
import urllib.request
import urllib.parse
import time
import re
from bs4 import BeautifulSoup

APP_DIR = "/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/apps/Agentic_Design_Patterns_Reader"
PAGES_DIR = os.path.join(APP_DIR, "data", "pages")
LOCALE_EN_DIR = os.path.join(APP_DIR, "data", "locales", "en")
LOCALE_VI_DIR = os.path.join(APP_DIR, "data", "locales", "vi")

os.makedirs(LOCALE_EN_DIR, exist_ok=True)
os.makedirs(LOCALE_VI_DIR, exist_ok=True)

def extract_page_en(page_num):
    html_path = os.path.join(PAGES_DIR, f"Agentic_Design_Patterns-{page_num}.html")
    if not os.path.exists(html_path):
        return None
    with open(html_path, 'r', encoding='ISO-8859-1') as f:
        html_content = f.read()
    soup = BeautifulSoup(html_content, 'html.parser')
    spans = soup.find_all('span')
    texts = {}
    for idx, span in enumerate(spans):
        texts[str(idx)] = span.get_text(strip=False)
    json_path = os.path.join(LOCALE_EN_DIR, f"page_{page_num}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(texts, f, ensure_ascii=False, indent=2)
    return texts

def translate_text(text):
    if not text.strip():
        return text
    url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=" + urllib.parse.quote(text)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode('utf-8'))
        translated_text = "".join([segment[0] for segment in data[0] if segment[0]])
        return translated_text
    except Exception as e:
        print("Error translating:", e)
        return text

def translate_page(page_num):
    en_json_path = os.path.join(LOCALE_EN_DIR, f"page_{page_num}.json")
    if not os.path.exists(en_json_path):
        texts = extract_page_en(page_num)
        if not texts: return
    else:
        with open(en_json_path, 'r', encoding='utf-8') as f:
            texts = json.load(f)
            
    vi_json_path = os.path.join(LOCALE_VI_DIR, f"page_{page_num}.json")
    
    # We will chunk the text using <br> to preserve newlines and batch translate
    # But text might have <br> already, we can use <hr> as separator
    keys = list(texts.keys())
    values = [texts[k] for k in keys]
    
    # Google Translate has a 5000 character limit per request.
    # We will chunk the values.
    translated_values = []
    
    current_chunk = []
    current_length = 0
    
    chunks = []
    
    for v in values:
        v_str = str(v).replace("<", "&lt;").replace(">", "&gt;") # escape html
        # separator
        sep = " <hr> "
        if current_length + len(v_str) + len(sep) > 4000:
            chunks.append(current_chunk)
            current_chunk = [v_str]
            current_length = len(v_str)
        else:
            current_chunk.append(v_str)
            current_length += len(v_str) + len(sep)
            
    if current_chunk:
        chunks.append(current_chunk)
        
    for chunk in chunks:
        joined_text = " <hr> ".join(chunk)
        res = translate_text(joined_text)
        # split back
        parts = res.split("<hr>")
        # sometimes GT adds spaces around <hr>
        parts = [p.strip().replace("&lt;", "<").replace("&gt;", ">") for p in parts]
        
        # fallback if parts count mismatch (due to GT messing up the <hr> tag)
        if len(parts) != len(chunk):
            print(f"Warning: Page {page_num} chunk mismatch! Expected {len(chunk)}, got {len(parts)}. Falling back to individual translation.")
            for item in chunk:
                item_res = translate_text(item.replace("&lt;", "<").replace("&gt;", ">"))
                translated_values.append(item_res)
                time.sleep(0.1)
        else:
            translated_values.extend(parts)
            
    translated_texts = {}
    for i, k in enumerate(keys):
        if i < len(translated_values):
            translated_texts[k] = translated_values[i]
        else:
            translated_texts[k] = texts[k]
            
    with open(vi_json_path, 'w', encoding='utf-8') as f:
        json.dump(translated_texts, f, ensure_ascii=False, indent=2)
        
    print(f"Translated page {page_num}")

if __name__ == '__main__':
    translate_page(4)
