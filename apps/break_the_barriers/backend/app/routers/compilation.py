import os
import shutil
import logging
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db, get_background_db
from backend.app.models import CompilationRequest
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.core import DATA_DIR
from backend.app.services.compiler import Compiler

logger = logging.getLogger(__name__)
router = APIRouter()


def _perform_compilation(doc_id: str, page_num: int, db: Session) -> dict:
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if page_num <= 0:
        raise HTTPException(status_code=400, detail="Invalid page number")
    page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    translations = db.query(DBTranslation).filter(
        DBTranslation.document_id == doc_id, DBTranslation.page_num == page_num
    ).all()
    translated_texts = {t.span_id: (t.translated_text or t.original_text) for t in translations}

    if not Compiler.verify_quality_gates(page.original_html, translated_texts):
        raise HTTPException(status_code=422, detail="Quality Gate 2 Failed: Mismatched tag count")

    compiled_html = Compiler.inject_translation(page.original_html, translated_texts)
    page.translated_html = compiled_html
    page.status = "compiled"

    compiled_dir = os.path.join(DATA_DIR, "pages", doc_id)
    os.makedirs(compiled_dir, exist_ok=True)
    with open(os.path.join(compiled_dir, f"page_{page_num}.html"), "w", encoding="utf-8") as f:
        f.write(compiled_html)

    extracted_dir = os.path.join(DATA_DIR, "extracted_html", doc_id)
    if os.path.exists(extracted_dir):
        for item in os.listdir(extracted_dir):
            if item.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                try:
                    shutil.copy2(os.path.join(extracted_dir, item), os.path.join(compiled_dir, item))
                except Exception:
                    pass

    all_pages = db.query(DBPage).filter(DBPage.document_id == doc_id).all()
    if all_pages and all(p.status == "compiled" for p in all_pages):
        doc.status = "compiled"
    db.commit()
    return {
        "status": "compiled", "doc_id": doc_id, "page_num": page_num,
        "html_path": f"data/pages/{doc_id}/page_{page_num}.html"
    }


def run_background_compile(doc_id: str, page_num: int):
    db = get_background_db()
    try:
        _perform_compilation(doc_id, page_num, db)
    except Exception as e:
        logger.error(f"Background compilation failed for {doc_id} page {page_num}: {e}")
        page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
        if page:
            page.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/api/docs/{doc_id}/compile")
def compile_page(
    doc_id: str, payload: CompilationRequest,
    async_mode: bool = Query(False),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    if payload.page_num <= 0:
        raise HTTPException(status_code=400, detail="Invalid page number")
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == payload.page_num).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if async_mode:
        page.status = "compiling"
        db.commit()
        if background_tasks:
            background_tasks.add_task(run_background_compile, doc_id, payload.page_num)
        else:
            run_background_compile(doc_id, payload.page_num)
        return JSONResponse(status_code=202, content={
            "status": "compiling", "doc_id": doc_id,
            "page_num": payload.page_num, "message": "Compilation started in background"
        })
    return _perform_compilation(doc_id, payload.page_num, db)
