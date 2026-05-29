import os
import re
import shutil
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, Depends
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import DocumentMetadata
from backend.app.models_db import DBDocument, DBPage, DBTranslation
from backend.app.core import DATA_DIR, estimate_pdf_pages
from backend.app.services.volume_detector import VolumeDetector
from backend.app.services.translator import Translator
from backend.app.services.compiler import Compiler

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
def get_status():
    return {"status": "online", "service": "Smart Documentations Backend", "docs_url": "/docs"}


@router.get("/api/docs", response_model=List[DocumentMetadata])
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(DBDocument).all()
    return [
        DocumentMetadata(
            id=d.id, filename=d.filename, total_pages=d.total_pages,
            status=d.status, created_at=d.created_at.isoformat()
        )
        for d in docs
    ]


@router.get("/api/docs/{doc_id}/pages")
def list_document_pages(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    pages = db.query(DBPage).filter(DBPage.document_id == doc_id).order_by(DBPage.page_num).all()
    return [
        {
            "page_num": p.page_num, "status": p.status,
            "has_original": p.original_html is not None,
            "has_translated": p.translated_html is not None
        }
        for p in pages
    ]


def _estimate_epub_chapters(content: bytes) -> int:
    try:
        import zipfile, io
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            html_count = sum(
                1 for name in zf.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
                and "META-INF" not in name
            )
            return max(html_count, 1)
    except Exception:
        return 5


@router.post("/api/docs/upload", response_model=DocumentMetadata)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    is_epub = file.filename.lower().endswith(".epub")
    is_pdf = file.filename.lower().endswith(".pdf")
    if not (is_pdf or is_epub):
        raise HTTPException(status_code=400, detail="Only PDF or EPUB files are supported")

    ext = ".epub" if is_epub else ".pdf"
    doc_id = os.path.splitext(file.filename)[0].lower().replace(" ", "_")
    file_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}{ext}")
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    if is_epub:
        estimated_pages = _estimate_epub_chapters(content)
    else:
        matches = re.findall(rb"/Count\s+(\d+)", content)
        estimated_pages = 10
        if matches:
            try:
                estimated_pages = max(int(m) for m in matches)
            except ValueError:
                pass

    # Auto-detect volume profile after upload
    volume = VolumeDetector.detect(page_count=estimated_pages)

    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        doc = DBDocument(
            id=doc_id, filename=file.filename, total_pages=estimated_pages, status="raw",
            volume_tier=volume.tier, quality_tier=volume.recommended_quality,
            estimated_cost_usd=volume.estimated_cost_usd,
            estimated_duration_min=volume.estimated_duration_min,
        )
        db.add(doc)
    else:
        doc.total_pages = estimated_pages
        doc.status = "raw"
        doc.volume_tier = volume.tier
        doc.quality_tier = volume.recommended_quality
        doc.estimated_cost_usd = volume.estimated_cost_usd
        doc.estimated_duration_min = volume.estimated_duration_min
    db.commit()
    db.refresh(doc)

    return DocumentMetadata(
        id=doc.id, filename=doc.filename, total_pages=doc.total_pages,
        status=doc.status, created_at=doc.created_at.isoformat()
    )


@router.delete("/api/docs/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
    for path in [os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.error(f"Failed to delete {path}: {e}")
    for dirpath in [
        os.path.join(DATA_DIR, "extracted_html", doc_id),
        os.path.join(DATA_DIR, "pages", doc_id),
    ]:
        if os.path.exists(dirpath):
            try:
                shutil.rmtree(dirpath)
            except Exception as e:
                logger.error(f"Failed to delete {dirpath}: {e}")
    return {"status": "deleted", "doc_id": doc_id, "message": "Document and all related assets deleted successfully"}


@router.get("/api/docs/{doc_id}/pdf")
def get_pdf_file(doc_id: str, page: Optional[int] = Query(None), db: Session = Depends(get_db)):
    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if page is not None:
        page_pdf_path = os.path.join(DATA_DIR, "raw_pdf", doc_id, f"{page}.pdf")
        if not os.path.exists(page_pdf_path):
            pdf_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")
            if not os.path.exists(pdf_path):
                raise HTTPException(status_code=404, detail="PDF file not found")
            try:
                from pypdf import PdfReader, PdfWriter
                reader = PdfReader(pdf_path)
                if page < 1 or page > len(reader.pages):
                    raise HTTPException(status_code=400, detail="Page number out of bounds")
                os.makedirs(os.path.join(DATA_DIR, "raw_pdf", doc_id), exist_ok=True)
                writer = PdfWriter()
                writer.add_page(reader.pages[page - 1])
                with open(page_pdf_path, "wb") as f:
                    writer.write(f)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to split PDF: {str(e)}")
        return FileResponse(page_pdf_path, media_type="application/pdf")
    pdf_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found")
    return FileResponse(pdf_path, media_type="application/pdf")


@router.get("/api/docs/{doc_id}/assets/{filename}")
def get_document_asset(doc_id: str, filename: str):
    file_path = os.path.join(DATA_DIR, "extracted_html", doc_id, filename)
    if not os.path.exists(file_path):
        file_path = os.path.join(DATA_DIR, "pages", doc_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = "application/octet-stream"
    if filename.lower().endswith(".png"):
        media_type = "image/png"
    elif filename.lower().endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif filename.lower().endswith(".gif"):
        media_type = "image/gif"
    return FileResponse(file_path, media_type=media_type)


@router.get("/api/docs/{doc_id}/pages/{page_num}")
def get_page_content(
    doc_id: str, page_num: int,
    lang: str = Query("en", pattern="^(en|vi)$"),
    raw: bool = Query(False),
    db: Session = Depends(get_db)
):
    from backend.app.services.compiler import Compiler
    from backend.app.services.translator import Translator
    from backend.app.models_db import DBTranslation

    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    page = db.query(DBPage).filter(DBPage.document_id == doc_id, DBPage.page_num == page_num).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if lang == "en":
        html = page.original_html
    else:
        if page.translated_html:
            html = page.translated_html
        else:
            translations = db.query(DBTranslation).filter(
                DBTranslation.document_id == doc_id,
                DBTranslation.page_num == page_num
            ).all()
            trans_dict = {}
            for t in translations:
                trans_dict[t.span_id] = t.translated_text or Translator.translate_text_agentic(t.original_text)
            html = Compiler.inject_translation(page.original_html, trans_dict)

    if raw:
        script_inject = """
<script>
window.addEventListener('load', () => {
    const div = document.querySelector('div[style*="width"]');
    if (div) {
        const styleAttr = div.getAttribute('style') || '';
        const wMatch = styleAttr.match(/width:\\s*(\\d+)/i);
        const hMatch = styleAttr.match(/height:\\s*(\\d+)/i);
        const w = wMatch ? parseInt(wMatch[1]) : (parseInt(div.style.width) || 900);
        const h = hMatch ? parseInt(hMatch[1]) : (parseInt(div.style.height) || 1260);
        window.parent.postMessage({ type: 'page_size', width: w, height: h, page_num: %d }, '*');
    } else {
        window.parent.postMessage({ type: 'page_size', width: 900, height: 1260, page_num: %d }, '*');
    }
});
</script>
""" % (page_num, page_num)
        if "</head>" in (html or "").lower():
            html_injected = html.replace("</head>", f"{script_inject}</head>", 1)
        elif "</body>" in (html or "").lower():
            html_injected = html.replace("</body>", f"{script_inject}</body>", 1)
        else:
            html_injected = (html or "") + script_inject
        return HTMLResponse(content=html_injected)

    return {"doc_id": doc_id, "page_num": page_num, "lang": lang, "html": html}
