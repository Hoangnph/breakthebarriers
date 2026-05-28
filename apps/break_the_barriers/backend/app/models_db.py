from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float
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

    # Phase 1 additions
    volume_tier = Column(String, nullable=True)
    quality_tier = Column(String, default="high")
    estimated_cost_usd = Column(Float, nullable=True)
    estimated_duration_min = Column(Integer, nullable=True)

    pages = relationship("DBPage", back_populates="document", cascade="all, delete-orphan")
    translations = relationship("DBTranslation", back_populates="document", cascade="all, delete-orphan")
    jobs = relationship("DBJob", back_populates="document", cascade="all, delete-orphan")


class DBPage(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_num = Column(Integer, nullable=False)
    original_html = Column(Text, nullable=True)
    translated_html = Column(Text, nullable=True)
    status = Column(String, default="raw")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
