import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db, SessionLocal
from backend.app.models_db import DBDocument, DBPage, DBJob

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/jobs/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(DBJob).filter(DBJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "doc_id": job.doc_id,
        "page_num": job.page_num,
        "stage": job.stage,
        "status": job.status,
        "volume_tier": job.volume_tier,
        "quality_tier": job.quality_tier,
        "retries": job.retries,
        "error_msg": job.error_msg,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/api/docs/{doc_id}/jobs")
def list_document_jobs(
    doc_id: str,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    query = db.query(DBJob).filter(DBJob.doc_id == doc_id)
    if status:
        query = query.filter(DBJob.status == status)
    jobs = query.order_by(DBJob.created_at).all()
    return [
        {
            "id": j.id,
            "page_num": j.page_num,
            "stage": j.stage,
            "status": j.status,
            "quality_tier": j.quality_tier,
            "retries": j.retries,
            "error_msg": j.error_msg,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@router.get("/api/docs/{doc_id}/progress")
async def progress_stream(doc_id: str):
    """SSE endpoint — stream translation progress for a document."""

    async def event_generator():
        max_iterations = 300  # safety: max 5 minutes
        for _ in range(max_iterations):
            db = SessionLocal()
            try:
                doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
                if not doc:
                    yield f"data: {json.dumps({'error': 'Document not found'})}\n\n"
                    return

                total = db.query(DBPage).filter(DBPage.document_id == doc_id).count()
                compiled = db.query(DBPage).filter(
                    DBPage.document_id == doc_id, DBPage.status == "compiled"
                ).count()
                translated = db.query(DBPage).filter(
                    DBPage.document_id == doc_id, DBPage.status == "translated"
                ).count()
                failed = db.query(DBPage).filter(
                    DBPage.document_id == doc_id, DBPage.status == "failed"
                ).count()

                done = compiled + translated
                percent = int((done / total) * 100) if total > 0 else 0
                remaining = total - done
                eta_min = max(0, int(remaining * 30 / 60))

                data = {
                    "total": total,
                    "compiled": compiled,
                    "translated": translated,
                    "failed": failed,
                    "percent": percent,
                    "eta_min": eta_min,
                    "status": "completed" if (done == total and total > 0) else "in_progress",
                }
                yield f"data: {json.dumps(data)}\n\n"

                if done == total and total > 0:
                    return
            finally:
                db.close()

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


STUCK_JOB_TIMEOUT_MINUTES = 30


@router.post("/api/docs/{doc_id}/resume")
async def resume_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 1. Mark stuck running jobs as failed (started > 30 min ago)
    stuck_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_JOB_TIMEOUT_MINUTES)
    stuck_jobs = (
        db.query(DBJob)
        .filter(
            DBJob.doc_id == doc_id,
            DBJob.status == "running",
            DBJob.started_at != None,
            DBJob.started_at < stuck_cutoff,
        )
        .all()
    )
    for job in stuck_jobs:
        job.status = "failed"
        job.error_msg = f"Timeout: job ran > {STUCK_JOB_TIMEOUT_MINUTES} minutes without completing"
    if stuck_jobs:
        db.commit()
        logger.info(f"Marked {len(stuck_jobs)} stuck jobs as failed for doc {doc_id}")

    # 2. Reset stuck translating pages to extracted (so they get re-translated)
    stuck_pages = (
        db.query(DBPage)
        .filter(DBPage.document_id == doc_id, DBPage.status == "translating")
        .all()
    )
    for page in stuck_pages:
        page.status = "extracted"
    if stuck_pages:
        db.commit()

    # 3. Survey page statuses
    all_pages = db.query(DBPage).filter(DBPage.document_id == doc_id).all()
    raw_pages = [p for p in all_pages if p.status == "raw"]
    translate_pages = [p for p in all_pages if p.status in ("extracted", "failed")]
    compile_pages = [p for p in all_pages if p.status == "translated"]

    tier = doc.volume_tier or "M"
    quality = doc.quality_tier or "high"
    queued = 0

    # 4. Re-extract if pages still raw
    if raw_pages:
        from backend.app.routers.extraction import run_background_extract
        background_tasks.add_task(run_background_extract, doc_id)
        queued += len(raw_pages)

    # 5. Re-translate extracted/failed pages
    if translate_pages:
        new_jobs = []
        for page in translate_pages:
            job = DBJob(
                doc_id=doc_id,
                page_num=page.page_num,
                stage="translate",
                status="pending",
                volume_tier=tier,
                quality_tier=quality,
            )
            db.add(job)
            new_jobs.append(job)
        db.commit()
        for job in new_jobs:
            db.refresh(job)

        jobs_data = [(job.id, job.page_num) for job in new_jobs]

        async def _dispatch_translate():
            from backend.app.services.job_manager import dispatch_all_translation_jobs
            await dispatch_all_translation_jobs(jobs_data, doc_id, "vi", quality, tier)

        background_tasks.add_task(_dispatch_translate)
        queued += len(translate_pages)

    # 6. Compile translated pages
    if compile_pages:
        from backend.app.routers.compilation import run_background_compile
        for page in compile_pages:
            background_tasks.add_task(run_background_compile, doc_id, page.page_num)
        queued += len(compile_pages)

    return {
        "status": "resumed" if queued > 0 else "nothing_to_do",
        "doc_id": doc_id,
        "queued": queued,
        "detail": {
            "raw_pages_re_extracted": len(raw_pages),
            "pages_re_translated": len(translate_pages),
            "pages_re_compiled": len(compile_pages),
            "stuck_jobs_reset": len(stuck_jobs),
        },
    }
