import logging
from backend.app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="backend.app.workers.tasks.translate_page_task",
    max_retries=3,
)
def translate_page_task(
    self,
    job_id: str,
    doc_id: str,
    page_num: int,
    target_lang: str,
    quality: str,
) -> dict:
    """Celery task for L/XL document page translation with exponential retry."""
    from backend.app.services.job_manager import _run_translation_job

    try:
        _run_translation_job(job_id, doc_id, page_num, target_lang, quality)
        return {"status": "done", "job_id": job_id, "page_num": page_num}
    except Exception as exc:
        logger.error(f"Celery task failed job={job_id} page={page_num}: {exc}")
        countdown = 30 * (2 ** self.request.retries)  # 30s, 60s, 120s
        raise self.retry(exc=exc, countdown=countdown)
