from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.app.database import get_db
from backend.app.models import VolumeProfileResponse
from backend.app.models_db import DBDocument
from backend.app.services.volume_detector import VolumeDetector

router = APIRouter()


@router.get("/api/docs/{doc_id}/volume", response_model=VolumeProfileResponse)
def get_volume_profile(
    doc_id: str,
    quality_override: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    profile = VolumeDetector.detect(page_count=doc.total_pages, quality_override=quality_override)
    return VolumeProfileResponse(
        tier=profile.tier,
        page_count=profile.page_count,
        estimated_spans=profile.estimated_spans,
        estimated_tokens=profile.estimated_tokens,
        estimated_cost_usd=profile.estimated_cost_usd,
        recommended_quality=profile.recommended_quality,
        processing_path=profile.processing_path,
        estimated_duration_min=profile.estimated_duration_min,
    )
