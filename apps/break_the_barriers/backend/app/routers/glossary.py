from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import GlossaryCreateRequest, GlossaryUpdateRequest, GlossaryEntry, GlossaryListResponse
from backend.app.models_db import DBDocument, DBDocumentGlossary

router = APIRouter()


def _to_entry(e: DBDocumentGlossary) -> GlossaryEntry:
    return GlossaryEntry(
        id=e.id, document_id=e.document_id, source_term=e.source_term,
        target_term=e.target_term, target_lang=e.target_lang, is_manual=e.is_manual,
    )


@router.get("/api/docs/{doc_id}/glossary", response_model=GlossaryListResponse)
def get_glossary(doc_id: str, lang: str = "vi", db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    entries = db.query(DBDocumentGlossary).filter(
        DBDocumentGlossary.document_id == doc_id,
        DBDocumentGlossary.target_lang == lang,
    ).all()
    return GlossaryListResponse(entries=[_to_entry(e) for e in entries], total=len(entries))


@router.post("/api/docs/{doc_id}/glossary", status_code=201, response_model=GlossaryEntry)
def add_glossary_entry(doc_id: str, payload: GlossaryCreateRequest, db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    existing = db.query(DBDocumentGlossary).filter(
        DBDocumentGlossary.document_id == doc_id,
        DBDocumentGlossary.source_term == payload.source_term,
        DBDocumentGlossary.target_lang == payload.target_lang,
    ).first()
    if existing:
        existing.target_term = payload.target_term
        existing.is_manual = payload.is_manual
        db.commit()
        db.refresh(existing)
        return _to_entry(existing)
    entry = DBDocumentGlossary(
        document_id=doc_id, source_term=payload.source_term,
        target_term=payload.target_term, target_lang=payload.target_lang,
        is_manual=payload.is_manual,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _to_entry(entry)


@router.put("/api/docs/{doc_id}/glossary/{entry_id}", response_model=GlossaryEntry)
def update_glossary_entry(
    doc_id: str, entry_id: str, payload: GlossaryUpdateRequest, db: Session = Depends(get_db)
):
    entry = db.query(DBDocumentGlossary).filter(
        DBDocumentGlossary.id == entry_id, DBDocumentGlossary.document_id == doc_id
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    entry.target_term = payload.target_term
    db.commit()
    db.refresh(entry)
    return _to_entry(entry)


@router.delete("/api/docs/{doc_id}/glossary/{entry_id}")
def delete_glossary_entry(doc_id: str, entry_id: str, db: Session = Depends(get_db)):
    entry = db.query(DBDocumentGlossary).filter(
        DBDocumentGlossary.id == entry_id, DBDocumentGlossary.document_id == doc_id
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    db.delete(entry)
    db.commit()
    return {"ok": True, "deleted_id": entry_id}
