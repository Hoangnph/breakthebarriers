import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
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
