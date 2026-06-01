import logging
from typing import List
from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

import json as _json
from backend.app.database import get_db, get_background_db
from backend.app.models import TranslationRequest, TranslationItem, TranslationUpdate, TranslateAllRequest, ExtractContextResponse
from backend.app.models_db import DBDocument, DBPage, DBTranslation, DBJob, DBDocumentGlossary
from backend.app.services.extractor import Extractor
from backend.app.services.translator import Translator
from backend.app.services.translator_v2 import TranslatorV2
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


async def _dispatch_all_jobs_background(
    jobs_data: list,
    doc_id: str,
    target_lang: str,
    quality: str,
    tier: str,
) -> None:
    """Async background task that fans out all page translation jobs via JobManager."""
    from backend.app.services.job_manager import dispatch_all_translation_jobs
    await dispatch_all_translation_jobs(jobs_data, doc_id, target_lang, quality, tier)


@router.post("/api/docs/{doc_id}/extract-context", response_model=ExtractContextResponse)
def extract_context(doc_id: str, payload: dict = None, db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    target_lang = (payload or {}).get("target_lang", "vi")

    pages = db.query(DBPage).filter(DBPage.document_id == doc_id).order_by(DBPage.page_num).limit(3).all()
    sample_html = [p.original_html or "" for p in pages]

    context = TranslatorV2.extract_document_context(doc_id, sample_html)
    doc.ai_metadata = _json.dumps(context)

    glossary_entries = TranslatorV2.build_glossary_from_context(doc_id, target_lang, context)
    for entry in glossary_entries:
        existing = db.query(DBDocumentGlossary).filter(
            DBDocumentGlossary.document_id == doc_id,
            DBDocumentGlossary.source_term == entry["source"],
            DBDocumentGlossary.target_lang == target_lang,
        ).first()
        if not existing:
            db.add(DBDocumentGlossary(
                document_id=doc_id,
                source_term=entry["source"],
                target_term=entry["target"],
                target_lang=target_lang,
                is_manual=False,
            ))
    db.commit()

    return ExtractContextResponse(
        doc_id=doc_id,
        title=context.get("title", doc.filename),
        author=context.get("author"),
        domain=context.get("domain", "general"),
        style=context.get("style", "formal_academic"),
        key_terms=context.get("key_terms", []),
    )


@router.post("/api/docs/{doc_id}/translate-all")
async def translate_all_pages(
    doc_id: str,
    payload: TranslateAllRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Only translate pages not yet compiled
    pages = (
        db.query(DBPage)
        .filter(DBPage.document_id == doc_id, DBPage.status != "compiled")
        .order_by(DBPage.page_num)
        .all()
    )
    if not pages:
        return {"status": "nothing_to_do", "doc_id": doc_id, "total_pages": 0, "job_ids": []}

    tier = doc.volume_tier or "M"
    quality = payload.quality_tier or doc.quality_tier or "high"

    # V2 pipeline: batch translation
    if getattr(payload, "use_v2", True):
        context_raw = doc.ai_metadata or "{}"
        try:
            context = _json.loads(context_raw)
        except Exception:
            context = {"title": doc.filename, "domain": "general", "style": "formal_academic"}

        glossary_rows = db.query(DBDocumentGlossary).filter(
            DBDocumentGlossary.document_id == doc_id,
            DBDocumentGlossary.target_lang == payload.target_lang,
        ).all()
        glossary = [{"source": g.source_term, "target": g.target_term} for g in glossary_rows]

        page_nums = [p.page_num for p in pages]

        def run_v2_translation():
            import asyncio
            async def _run():
                sem = asyncio.Semaphore(3)
                async def translate_one(pnum):
                    async with sem:
                        loop = asyncio.get_event_loop()
                        bg_db = get_background_db()
                        try:
                            await loop.run_in_executor(None, lambda: TranslatorV2.translate_page_batch(
                                doc_id=doc_id, page_num=pnum,
                                target_lang=payload.target_lang,
                                context=context, glossary=glossary,
                                db=bg_db, quality=quality,
                            ))
                        finally:
                            bg_db.close()
                await asyncio.gather(*[translate_one(p) for p in page_nums])
            asyncio.run(_run())

        # Mark pages as translating
        for p in pages:
            p.status = "translating"
        db.commit()

        background_tasks.add_task(run_v2_translation)
        return {
            "status": "started_v2",
            "doc_id": doc_id,
            "total_pages": len(page_nums),
            "quality_tier": quality,
        }

    # Create a DBJob record per page before dispatching
    created_jobs = []
    for page in pages:
        job = DBJob(
            doc_id=doc_id,
            page_num=page.page_num,
            stage="translate",
            status="pending",
            volume_tier=tier,
            quality_tier=quality,
        )
        db.add(job)
        created_jobs.append(job)
    db.commit()
    for job in created_jobs:
        db.refresh(job)

    jobs_data = [(job.id, job.page_num) for job in created_jobs]

    background_tasks.add_task(
        _dispatch_all_jobs_background,
        jobs_data,
        doc_id,
        payload.target_lang,
        quality,
        tier,
    )

    return {
        "status": "started",
        "doc_id": doc_id,
        "total_pages": len(created_jobs),
        "quality_tier": quality,
        "volume_tier": tier,
        "job_ids": [j.id for j in created_jobs],
    }
