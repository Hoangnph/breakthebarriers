from pydantic import BaseModel
from typing import List, Dict, Optional

class DocumentMetadata(BaseModel):
    id: str
    filename: str
    total_pages: int
    status: str  # "raw", "extracted", "translated", "compiled"
    created_at: str

class ExtractionResult(BaseModel):
    id: str
    pages_count: int
    extracted_html_dir: str

class TranslationRequest(BaseModel):
    page_num: int
    target_lang: str = "vi"
    quality_tier: str = "high"

class CompilationRequest(BaseModel):
    page_num: int

class TranslationItem(BaseModel):
    id: int
    document_id: str
    page_num: int
    span_id: str
    original_text: str
    translated_text: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True

class TranslationUpdate(BaseModel):
    translated_text: str


class VolumeProfileResponse(BaseModel):
    tier: str
    page_count: int
    estimated_spans: int
    estimated_tokens: int
    estimated_cost_usd: float
    recommended_quality: str
    processing_path: str
    estimated_duration_min: int


class TranslateAllRequest(BaseModel):
    target_lang: str = "vi"
    quality_tier: Optional[str] = None
