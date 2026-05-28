import logging
from typing import List
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.app.database import get_db, get_background_db
from backend.app.models import TranslationRequest, TranslationItem, TranslationUpdate
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.services.extractor import Extractor
from backend.app.services.translator import Translator
from backend.app.routers.compilation import _perform_compilation

logger = logging.getLogger(__name__)
router = APIRouter()


def _perform_translation(doc_id: str, page_num: int, target_lang: str, db: Session, quality: str = "high") -> dict:
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if page_num <= 0:
        raise HTTPException(status_code=400, detail="Invalid page number")
    page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    page.translated_html = None
    spans_list = Extractor.extract_spans(page.original_html)
    reconstructed = Translator.reconstruct_context_and_index(spans_list)

    for block in reconstructed:
        translated_block = Translator.translate_text_agentic(block["text"], target_lang=target_lang, quality=quality)
        if len(block["span_ids"]) == 1:
            span_id = block["span_ids"][0]
            t_row = db.query(DBTranslation).filter(
                DBTranslation.document_id == doc_id, DBTranslation.page_num == page_num,
                DBTranslation.span_id == span_id
            ).first()
            if t_row:
                t_row.translated_text = translated_block
        else:
            span_translations = Translator.deinterpolate_translation(translated_block, block["span_ids"])
            for sid, text in span_translations.items():
                t_row = db.query(DBTranslation).filter(
                    DBTranslation.document_id == doc_id, DBTranslation.page_num == page_num,
                    DBTranslation.span_id == sid
                ).first()
                if t_row:
                    t_row.translated_text = text

    page.status = "translated"
    all_pages = db.query(DBPage).filter(DBPage.document_id == doc_id).all()
    if all_pages and all(p.status in ["translated", "compiled"] for p in all_pages):
        doc.status = "translated"
    db.commit()
    return {"status": "translated", "doc_id": doc_id, "page_num": page_num, "target_lang": target_lang}


def run_background_translate(doc_id: str, page_num: int, target_lang: str, quality: str = "high"):
    db = get_background_db()
    try:
        _perform_translation(doc_id, page_num, target_lang, db, quality)
    except Exception as e:
        logger.error(f"Background translation failed for {doc_id} page {page_num}: {e}")
        page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
        if page:
            page.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/api/docs/{doc_id}/translate")
def translate_page(
    doc_id: str, payload: TranslationRequest,
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
    quality = getattr(payload, "quality_tier", "high") or "high"

    if async_mode:
        page.status = "translating"
        db.commit()
        if background_tasks:
            background_tasks.add_task(run_background_translate, doc_id, payload.page_num, payload.target_lang, quality)
        else:
            run_background_translate(doc_id, payload.page_num, payload.target_lang, quality)
        return JSONResponse(status_code=202, content={
            "status": "translating", "doc_id": doc_id,
            "page_num": payload.page_num, "message": "Translation started in background"
        })
    return _perform_translation(doc_id, payload.page_num, payload.target_lang, db, quality)


@router.get("/api/docs/{doc_id}/translations", response_model=List[TranslationItem])
def list_translations(
    doc_id: str,
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    translations = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id)\
        .order_by(DBTranslation.page_num, DBTranslation.id).offset(offset).limit(limit).all()
    return [TranslationItem(
        id=t.id, document_id=t.document_id, page_num=t.page_num, span_id=t.span_id,
        original_text=t.original_text, translated_text=t.translated_text,
        created_at=t.created_at.isoformat()
    ) for t in translations]


@router.get("/api/docs/{doc_id}/translations/search", response_model=List[TranslationItem])
def search_translations(doc_id: str, q: str = Query(...), db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    translations = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id)\
        .filter(or_(
            DBTranslation.original_text.ilike(f"%{q}%"),
            DBTranslation.translated_text.ilike(f"%{q}%")
        )).order_by(DBTranslation.page_num, DBTranslation.id).all()
    return [TranslationItem(
        id=t.id, document_id=t.document_id, page_num=t.page_num, span_id=t.span_id,
        original_text=t.original_text, translated_text=t.translated_text,
        created_at=t.created_at.isoformat()
    ) for t in translations]


@router.put("/api/docs/{doc_id}/translations/{span_id}")
def update_translation(doc_id: str, span_id: str, payload: TranslationUpdate, db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    translations = db.query(DBTranslation).filter(
        DBTranslation.document_id == doc_id, DBTranslation.span_id == span_id
    ).all()
    if not translations:
        raise HTTPException(status_code=404, detail="Translation span not found in document")
    for t in translations:
        t.translated_text = payload.translated_text
    db.commit()
    affected_pages = sorted({t.page_num for t in translations})
    recompiled_pages = []
    for page_num in affected_pages:
        page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
        if page and page.status == "compiled":
            try:
                _perform_compilation(doc_id, page_num, db)
                recompiled_pages.append(page_num)
            except Exception as e:
                logger.error(f"Auto Re-compile failed for page {page_num}: {e}")
    return {
        "status": "updated",
        "span_id": span_id,
        "translated_text": payload.translated_text,
        "affected_pages": affected_pages,
        "recompiled_pages": recompiled_pages,
        "message": f"Translation updated and {len(recompiled_pages)} affected pages re-compiled successfully"
    }
