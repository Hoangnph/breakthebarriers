import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.database import SessionLocal
from backend.app.models_db import DBPage
from backend.app.services.extractor import Extractor

def check_spans():
    db = SessionLocal()
    try:
        page = db.query(DBPage).filter(
            DBPage.document_id == "daoduckinh-laotu_nguyenduycan",
            DBPage.page_num == 1
        ).first()
        if page:
            spans = Extractor.extract_spans(page.original_html)
            print(f"Successfully extracted {len(spans)} spans from page 1 HTML!")
            if spans:
                print("First 5 spans:")
                for s in spans[:5]:
                    print(s)
        else:
            print("Page not found")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_spans()
