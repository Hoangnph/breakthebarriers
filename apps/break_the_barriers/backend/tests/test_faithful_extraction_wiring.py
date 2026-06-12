import os
import shutil
from backend.app.services.faithful_extractor import FaithfulExtractor
from backend.app.routers.extraction import _perform_extraction
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.core import DATA_DIR
import backend.app.routers.extraction as extraction_module


def test_extraction_populates_faithful_columns(db_session, sample_pdf, monkeypatch):
    monkeypatch.setattr(FaithfulExtractor, "_docling_structure", staticmethod(lambda p: None))
    monkeypatch.setattr(extraction_module, "is_mock_run", lambda doc_id: False)
    doc_id = "wiretest"
    raw_dir = os.path.join(DATA_DIR, "raw_pdf")
    os.makedirs(raw_dir, exist_ok=True)
    shutil.copy(sample_pdf, os.path.join(raw_dir, f"{doc_id}.pdf"))

    db_session.add(DBDocument(id=doc_id, filename="sample.pdf", total_pages=1, status="raw"))
    db_session.commit()

    _perform_extraction(doc_id, db_session)

    page = db_session.query(DBPage).filter_by(document_id=doc_id, page_num=1).first()
    assert page is not None
    assert page.svg_path == f"{doc_id}-1.svg"
    assert page.text_layer_json and "spans" in page.text_layer_json
    assert 'id="s1"' in page.original_html
    trans = db_session.query(DBTranslation).filter_by(document_id=doc_id).all()
    assert any("Heading" in t.original_text for t in trans)

    os.remove(os.path.join(raw_dir, f"{doc_id}.pdf"))
    shutil.rmtree(os.path.join(DATA_DIR, "extracted_html", doc_id), ignore_errors=True)
