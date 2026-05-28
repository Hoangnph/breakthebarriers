from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base

class DBDocument(Base):
    __tablename__ = "documents"

    # doc_id (e.g. 'clean_code') is string primary key
    id = Column(String, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    total_pages = Column(Integer, default=0)
    status = Column(String, default="raw")  # raw, extracted, translated, compiled
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships with cascading deletes
    pages = relationship("DBPage", back_populates="document", cascade="all, delete-orphan")
    translations = relationship("DBTranslation", back_populates="document", cascade="all, delete-orphan")

class DBPage(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_num = Column(Integer, nullable=False)
    original_html = Column(Text, nullable=True)
    translated_html = Column(Text, nullable=True)
    status = Column(String, default="raw")  # raw, translated, compiled
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
