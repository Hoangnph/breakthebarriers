import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Tuple

from backend.app.database import get_background_db
from backend.app.models_db import DBJob, DBPage

logger = logging.getLogger(__name__)

# Concurrency limits per volume tier
SEMAPHORE_LIMITS = {
    "S": 3,
    "M": 8,
    "L": 10,   # Phase 3 routes L/XL to Celery
    "XL": 5,
}

# Lazily created semaphores — keyed by tier
_semaphores: dict = {}


def _get_semaphore(tier: str) -> asyncio.Semaphore:
    if tier not in _semaphores:
        limit = SEMAPHORE_LIMITS.get(tier, SEMAPHORE_LIMITS["M"])
        _semaphores[tier] = asyncio.Semaphore(limit)
    return _semaphores[tier]


def dispatch_celery_job(
    job_id: str, doc_id: str, page_num: int, target_lang: str, quality: str, tier: str
) -> str:
    """Send job to Celery queue. L → celery-high, XL → celery-low."""
    from backend.app.workers.tasks import translate_page_task

    queue = "celery-high" if tier == "L" else "celery-low"
    result = translate_page_task.apply_async(
        args=[job_id, doc_id, page_num, target_lang, quality],
        queue=queue,
    )
    return result.id


def _run_translation_job(
    job_id: str, doc_id: str, page_num: int, target_lang: str, quality: str
) -> None:
    """Synchronous — safe to run in ThreadPoolExecutor. Creates its own DB session."""
    from backend.app.routers.translation import _perform_translation

    db = get_background_db()
    try:
        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if job:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            db.commit()

        _perform_translation(doc_id, page_num, target_lang, db, quality)

        job = db.query(DBJob).filter(DBJob.id == job_id).first()
        if job:
            job.status = "done"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

    except Exception as e:
        logger.error(f"Translation job {job_id} (doc={doc_id} page={page_num}) failed: {e}")
        try:
            job = db.query(DBJob).filter(DBJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_msg = str(e)[:500]
                job.retries += 1
                db.commit()
            page = db.query(DBPage).filter(
                DBPage.document_id == doc_id, DBPage.page_num == page_num
            ).first()
            if page:
                page.status = "failed"
                db.commit()
        except Exception as inner:
            logger.error(f"Failed to update job status after error: {inner}")
    finally:
        db.close()


async def dispatch_translation_job(
    job_id: str, doc_id: str, page_num: int, target_lang: str, quality: str, tier: str
) -> None:
    """Async — acquires semaphore then runs blocking job in thread pool."""
    semaphore = _get_semaphore(tier)
    async with semaphore:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _run_translation_job,
            job_id, doc_id, page_num, target_lang, quality,
        )


async def dispatch_all_translation_jobs(
    jobs: List[Tuple[str, int]],
    doc_id: str,
    target_lang: str,
    quality: str,
    tier: str,
) -> None:
    """Route: S/M → asyncio semaphore pool, L/XL → Celery priority queues."""
    if tier in ("L", "XL"):
        # Celery path — dispatch synchronously, store task IDs
        celery_ids: dict = {}
        for job_id, page_num in jobs:
            task_id = dispatch_celery_job(job_id, doc_id, page_num, target_lang, quality, tier)
            celery_ids[job_id] = task_id
            logger.info(f"Queued Celery task {task_id} for job {job_id} page {page_num} tier {tier}")

        # Persist celery_task_id + mark as running in DB
        db = get_background_db()
        try:
            from backend.app.models_db import DBJob
            for job_id, task_id in celery_ids.items():
                job = db.query(DBJob).filter(DBJob.id == job_id).first()
                if job:
                    job.celery_task_id = task_id
                    job.status = "running"
            db.commit()
        finally:
            db.close()
    else:
        # asyncio path — S/M with semaphore concurrency control
        tasks = [
            dispatch_translation_job(job_id, doc_id, page_num, target_lang, quality, tier)
            for job_id, page_num in jobs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                job_id, page_num = jobs[i]
                logger.error(f"Job {job_id} page {page_num} unhandled exception: {result}")
