import os
import sys

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.database import SessionLocal
from backend.app.models_db import DBDocument, DBPage, DBTranslation

def check():
    db = SessionLocal()
    try:
        docs = db.query(DBDocument).all()
        print("=== DOCUMENTS ===")
        for d in docs:
            print(f"ID: {d.id} | Filename: {d.filename} | Status: {d.status} | Total Pages: {d.total_pages}")
            
            # Print page count
            pages = db.query(DBPage).filter(DBPage.document_id == d.id).all()
            print(f"  Pages in DB: {len(pages)}")
            
            # Print translation count
            translations = db.query(DBTranslation).filter(DBTranslation.document_id == d.id).all()
            print(f"  Translations in DB: {len(translations)}")
            print("-" * 40)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check()
