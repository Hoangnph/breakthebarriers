from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base


class DBDocument(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    total_pages = Column(Integer, default=0)
    status = Column(String, default="raw")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    volume_tier = Column(String, nullable=True)
    quality_tier = Column(String, default="high")
    estimated_cost_usd = Column(Float, nullable=True)
    estimated_duration_min = Column(Integer, nullable=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_public = Column(Boolean, default=False)
    ai_metadata = Column(Text, default='{}')  # JSON string: {title, author, domain, style}

    pages = relationship("DBPage", back_populates="document", cascade="all, delete-orphan")
    translations = relationship("DBTranslation", back_populates="document", cascade="all, delete-orphan")
    jobs = relationship("DBJob", back_populates="document", cascade="all, delete-orphan")
    user = relationship("DBUser", back_populates="documents")


class DBPage(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_num = Column(Integer, nullable=False)
    original_html = Column(Text, nullable=True)
    translated_html = Column(Text, nullable=True)
    status = Column(String, default="raw")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    needs_review        = Column(Boolean, default=False)
    review_reason       = Column(Text, nullable=True)
    translation_quality = Column(Float, nullable=True)
    layout_json         = Column(Text, nullable=True)
    model_json          = Column(Text, nullable=True)   # PageModel JSON (SP-A)
    svg_path            = Column(Text, nullable=True)   # faithful visual: "{doc}-{n}.svg" hoặc ".jpg"
    text_layer_json     = Column(Text, nullable=True)   # lớp text vô hình view Gốc

    document = relationship("DBDocument", back_populates="pages")


class DBTranslation(Base):
    __tablename__ = "translations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_num = Column(Integer, nullable=False)
    span_id = Column(String, nullable=False)
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("DBDocument", back_populates="translations")


class DBJob(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    doc_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_num = Column(Integer, nullable=True)
    stage = Column(String, nullable=False)
    status = Column(String, default="pending", index=True)
    volume_tier = Column(String, nullable=False)
    quality_tier = Column(String, default="high")
    retries = Column(Integer, default=0)
    error_msg = Column(Text, nullable=True)
    celery_task_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    document = relationship("DBDocument", back_populates="jobs")


class DBUser(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, default="")
    plan = Column(String, default="free")
    pages_used_this_month = Column(Integer, default=0)
    pages_limit = Column(Integer, default=20)
    pages_reset_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    documents = relationship("DBDocument", back_populates="user", lazy="write_only")
    subscriptions = relationship("DBSubscription", back_populates="user", cascade="all, delete-orphan")


class DBSubscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stripe_subscription_id = Column(String, unique=True, nullable=True)
    status = Column(String, default="active")
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("DBUser", back_populates="subscriptions")


class DBPublishedBook(Base):
    __tablename__ = "published_books"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    cover_url = Column(String, nullable=True)
    cover_path = Column(String, nullable=True)
    languages = Column(Text, default='["vi"]')  # JSON-encoded list, stored as Text for SQLite compat
    is_public = Column(Boolean, default=True)
    published_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DBDocumentGlossary(Base):
    __tablename__ = "document_glossaries"

    id          = Column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    source_term = Column(Text, nullable=False)
    target_term = Column(Text, nullable=False)
    target_lang = Column(String(10), nullable=False)
    is_manual   = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DBTranslationMemory(Base):
    __tablename__ = "translation_memory"

    source_hash = Column(String(64), primary_key=True)  # sha256(source_text + "|" + target_lang)
    source_text = Column(Text, nullable=False)
    target_lang = Column(String(10), nullable=False)
    translated  = Column(Text, nullable=False)
    quality     = Column(Float, default=1.0)
    hit_count   = Column(Integer, default=0)
    last_used   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
