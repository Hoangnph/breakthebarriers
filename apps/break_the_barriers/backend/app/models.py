from pydantic import BaseModel, ConfigDict, field_validator
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
    use_v2: bool = True

class PagePolicyRequest(BaseModel):
    value: str   # auto | base-color | keep-raster | clean-photo

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

    model_config = ConfigDict(from_attributes=True)

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
    use_v2: bool = True

class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str = ""

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

class UserLogin(BaseModel):
    email: str
    password: str

class UserInfo(BaseModel):
    id: str
    email: str
    full_name: str = ""
    plan: str
    pages_limit: int
    pages_used_this_month: int

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class PublishRequest(BaseModel):
    slug: str
    title: str
    description: str = ""
    languages: List[str] = ["vi"]
    is_public: bool = True
    cover_url: Optional[str] = None


class BookInfo(BaseModel):
    slug: str
    title: str
    description: str
    cover_url: Optional[str] = None
    languages: List[str]
    is_public: bool
    page_count: int
    published_at: str
    book_url: str


class BookPageInfo(BaseModel):
    page_number: int
    preview: str


class BookPageContent(BaseModel):
    page_number: int
    total_pages: int
    lang: str
    html: str
    prev_page: Optional[int] = None
    next_page: Optional[int] = None


class BookListResponse(BaseModel):
    books: List[BookInfo]
    total: int
    page: int
    per_page: int


class GlossaryEntry(BaseModel):
    id: str
    document_id: str
    source_term: str
    target_term: str
    target_lang: str
    is_manual: bool = False


class GlossaryCreateRequest(BaseModel):
    source_term: str
    target_term: str
    target_lang: str = "vi"
    is_manual: bool = True


class GlossaryUpdateRequest(BaseModel):
    target_term: str


class GlossaryListResponse(BaseModel):
    entries: List[GlossaryEntry]
    total: int


class ExtractContextResponse(BaseModel):
    doc_id: str
    title: str
    author: Optional[str] = None
    domain: str
    style: str
    key_terms: List[str]
