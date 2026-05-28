import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.database import SessionLocal
from backend.app.models_db import DBPage
from bs4 import BeautifulSoup

def check_html():
    db = SessionLocal()
    try:
        page = db.query(DBPage).filter(
            DBPage.document_id == "daoduckinh-laotu_nguyenduycan",
            DBPage.page_num == 1
        ).first()
        if page:
            print("=== PAGE 1 BODY ===")
            soup = BeautifulSoup(page.original_html, "html.parser")
            body_div = soup.find("div", style=lambda s: s and "relative" in s)
            if body_div:
                # print first 15 children
                children = [str(c) for c in body_div.contents if c.name][:15]
                for c in children:
                    print(c)
            else:
                print("relative div not found")
        else:
            print("Page not found")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_html()
