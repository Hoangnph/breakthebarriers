import os
import re
import shutil
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import DocumentMetadata, PagePolicyRequest
from backend.app.models_db import DBDocument, DBPage, DBTranslation, DBUser
from backend.app.dependencies import get_optional_user
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
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[DBUser] = Depends(get_optional_user),
):
    is_epub = file.filename.lower().endswith(".epub")
    is_pdf = file.filename.lower().endswith(".pdf")
    if not (is_pdf or is_epub):
        raise HTTPException(status_code=400, detail="Only PDF or EPUB files are supported")

    # Sanitize filename to prevent path traversal
    safe_name = os.path.basename(file.filename)
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    ext = ".epub" if is_epub else ".pdf"
    doc_id = os.path.splitext(safe_name)[0].lower().replace(" ", "_")
    content = await file.read()

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

    # Quota check before touching disk or DB — re-fetch with row lock for atomicity
    if current_user is not None:
        locked_user = db.query(DBUser).filter(DBUser.id == current_user.id).with_for_update().first()
        if (locked_user and not locked_user.is_admin
                and locked_user.pages_used_this_month + estimated_pages > locked_user.pages_limit):
            raise HTTPException(
                status_code=402,
                detail=f"Quota exceeded ({locked_user.pages_used_this_month}/{locked_user.pages_limit} pages used). Please upgrade your plan."
            )
        current_user = locked_user  # use the freshly locked instance

    # Write file to disk only after quota check passes
    file_path = os.path.join(DATA_DIR, "raw_pdf", f"{doc_id}{ext}")
    with open(file_path, "wb") as f:
        f.write(content)

    volume = VolumeDetector.detect(page_count=estimated_pages)

    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        doc = DBDocument(
            id=doc_id,
            filename=safe_name,
            total_pages=estimated_pages,
            status="raw",
            volume_tier=volume.tier,
            quality_tier=volume.recommended_quality,
            estimated_cost_usd=volume.estimated_cost_usd,
            estimated_duration_min=volume.estimated_duration_min,
            user_id=current_user.id if current_user else None,
        )
        db.add(doc)
    else:
        doc.total_pages = estimated_pages
        doc.status = "raw"
        doc.volume_tier = volume.tier
        doc.quality_tier = volume.recommended_quality
        doc.estimated_cost_usd = volume.estimated_cost_usd
        doc.estimated_duration_min = volume.estimated_duration_min
        if current_user:
            doc.user_id = current_user.id

    # Increment quota in the same transaction (admins are not metered)
    if current_user is not None and not current_user.is_admin:
        current_user.pages_used_this_month += estimated_pages

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
    elif filename.lower().endswith(".svg"):
        media_type = "image/svg+xml"
    return FileResponse(file_path, media_type=media_type)


def _inject_page_size(html: str, page_num: int, w, h) -> str:
    script = (
        "<script>window.addEventListener('load',()=>{"
        "window.parent.postMessage({type:'page_size',width:%d,height:%d,page_num:%d},'*');"
        "});</script>" % (int(w), int(h), page_num))
    low = (html or "").lower()
    if "</head>" in low:
        return html.replace("</head>", script + "</head>", 1)
    if "</body>" in low:
        return html.replace("</body>", script + "</body>", 1)
    return (html or "") + script


@router.get("/api/docs/{doc_id}/pages/{page_num}")
def get_page_content(
    doc_id: str, page_num: int,
    request: Request,
    lang: str = Query("en", pattern="^(en|vi)$"),
    raw: bool = Query(False),
    view: Optional[str] = Query(None, pattern="^(goc|dich)$"),
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

    if view is not None:
        if view == "goc":
            import json as _json
            import os as _os
            from backend.app.core import DATA_DIR as _DATA
            from backend.app.services.faithful_renderer import render_faithful_page
            tl = _json.loads(page.text_layer_json) if page.text_layer_json else {"spans": []}
            pw = tl.get("page_w") or 900.0
            ph = tl.get("page_h") or 1260.0
            visual = page.svg_path or ""
            asset_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
            if visual.endswith(".svg"):
                svg_file = _os.path.join(_DATA, "extracted_html", doc_id, visual)
                svg = "<svg></svg>"
                if _os.path.exists(svg_file):
                    with open(svg_file, "r", encoding="utf-8") as _sf:
                        svg = _sf.read()
                html = render_faithful_page(svg, "svg", tl, pw, ph)
            else:
                html = render_faithful_page(visual, "image", tl, pw, ph, asset_base)
            if raw:
                return HTMLResponse(content=_inject_page_size(html, page_num, pw, ph))
        else:  # view == "dich"
            rows = db.query(DBTranslation).filter(
                DBTranslation.document_id == doc_id, DBTranslation.page_num == page_num).all()
            trans_dict = {t.span_id: (t.translated_text or t.original_text or "") for t in rows}
            html = Compiler.inject_translation(page.original_html or "", trans_dict)
            if raw:
                return HTMLResponse(content=_inject_page_size(html, page_num, 900, 1260))
        return {"doc_id": doc_id, "page_num": page_num, "lang": lang, "view": view,
                "html": html, "page_class": "text", "cover": "none",
                "policy_override": None, "has_clean_image": False}

    # Prefer the rich PageModel when present (SP-A). Falls back to layout_json below.
    html = None
    if page.model_json:
        try:
            from backend.app.services.page_model import PageModel
            from backend.app.services.page_renderer import render_page
            pm = PageModel.from_json(page.model_json)
            pm.page_num = page_num
            image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
            rows = db.query(DBTranslation).filter(
                DBTranslation.document_id == doc_id,
                DBTranslation.page_num == page_num).all()
            if lang == "en":
                trans_dict = {t.span_id: (t.original_text or "") for t in rows}
            else:
                trans_dict = {t.span_id: (t.translated_text or "") for t in rows}
            html = render_page(pm, trans_dict, image_base)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"PageModel render failed for {doc_id} p{page_num}, falling back: {e}")
            html = None

    if html is None:
        import json as _json
        from backend.app.services.overlay_renderer import render_overlay_html

        layout = None
        if page.layout_json:
            try:
                parsed = _json.loads(page.layout_json)
                if parsed.get("image"):
                    layout = parsed
            except Exception:
                layout = None
        # Absolute URL to the backend so the raster <img> resolves against the API host,
        # not the frontend origin (the HTML is injected via dangerouslySetInnerHTML there).
        image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"

        if lang == "en":
            if layout:
                html = render_overlay_html(layout, {}, image_base)   # raster gốc, không overlay
            else:
                html = page.original_html
        else:
            if layout:
                translations = db.query(DBTranslation).filter(
                    DBTranslation.document_id == doc_id,
                    DBTranslation.page_num == page_num
                ).all()
                trans_dict = {t.span_id: (t.translated_text or "") for t in translations}
                html = render_overlay_html(layout, trans_dict, image_base)
            elif page.translated_html:
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

    page_class, cover = "text", "none"
    policy_override, has_clean_image = None, False
    if page.model_json:
        try:
            from backend.app.services.page_model import PageModel
            # Re-parse here (not reuse the render-block `pm`, which is unbound on
            # the layout_json fallback path) to read metadata fields safely.
            _pm = PageModel.from_json(page.model_json)
            page_class, cover = _pm.page_class, _pm.cover
            _bg = _pm.background or {}
            policy_override = _bg.get("policy_override")
            has_clean_image = bool(_bg.get("clean_image"))
        except Exception:
            pass
    return {"doc_id": doc_id, "page_num": page_num, "lang": lang, "html": html,
            "page_class": page_class, "cover": cover,
            "policy_override": policy_override, "has_clean_image": has_clean_image}


@router.get("/api/docs/{doc_id}/flow")
def get_document_flow(doc_id: str, request: Request,
                      lang: str = Query("vi", pattern="^(en|vi)$"),
                      db: Session = Depends(get_db)):
    # B2.2 — faithful flow: a vertical stack of per-page fragments (original raster +
    # masked translated overlay). `lang` selects original vs translated text.
    from backend.app.services.page_model import PageModel
    from backend.app.services.faithful_flow_renderer import render_faithful_flow
    from backend.app.models_db import DBTranslation

    doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    page_rows = (db.query(DBPage).filter(DBPage.document_id == doc_id)
                 .order_by(DBPage.page_num).all())
    pages = []
    for pr in page_rows:
        if pr.model_json:
            try:
                pm = PageModel.from_json(pr.model_json)
                pm.page_num = pr.page_num
                pages.append(pm)
            except Exception:
                pass
    from backend.app.services.toc_parser import (
        is_toc_page, extract_toc_entries, map_entry_to_page)

    rows = db.query(DBTranslation).filter(DBTranslation.document_id == doc_id).all()
    translations: dict = {}
    orig: dict = {}
    for t in rows:
        txt = (t.original_text if lang == "en" else t.translated_text) or ""
        translations.setdefault(t.page_num, {})[t.span_id] = txt
        orig.setdefault(t.page_num, {})[t.span_id] = t.original_text or ""

    # Hybrid TOC nav: list from the printed TOC, target page resolved by heading match.
    page_headings: list = []          # (page_num, original heading text)
    thead: dict = {}                  # page_num -> translated heading (nav label)
    for pm in pages:
        o = orig.get(pm.page_num, {})
        tm = translations.get(pm.page_num, {})
        for b in pm.blocks:
            if b.role == "heading":
                oh = o.get(b.span_id, "")
                if oh:
                    page_headings.append((pm.page_num, oh))
                if pm.page_num not in thead:
                    th = tm.get(b.span_id, "") or oh
                    if th:
                        thead[pm.page_num] = th
    nav = None
    for pm in pages:
        o = orig.get(pm.page_num, {})
        texts = [o.get(b.span_id, "") for b in pm.blocks]
        if is_toc_page(texts):
            nav = []
            for title, num in extract_toc_entries(texts):
                target = map_entry_to_page(title, page_headings, num)
                if target is not None:
                    nav.append((thead.get(target, title), target))
            break

    image_base = f"{str(request.base_url).rstrip('/')}/api/docs/{doc_id}/assets"
    html = render_faithful_flow(pages, translations, image_base, nav=nav)
    return HTMLResponse(content=html)


@router.post("/api/docs/{doc_id}/pages/{page_num}/clean-bg")
def clean_page_bg(doc_id: str, page_num: int,
                  method: str = Query("inpaint"), force: bool = Query(False),
                  db: Session = Depends(get_db)):
    from backend.app.services.page_model import PageModel
    from backend.app.services import image_cleaner

    page = db.query(DBPage).filter(DBPage.document_id == doc_id,
                                   DBPage.page_num == page_num).first()
    if not page or not page.model_json:
        raise HTTPException(status_code=404, detail="Page or model not found")
    pm = PageModel.from_json(page.model_json)
    from backend.app.services.background_policy import effective_policy
    if effective_policy(pm.page_class, pm.cover,
                        (pm.background or {}).get("policy_override")) != "clean-photo":
        raise HTTPException(status_code=400, detail="Page is not a clean-photo page")
    src_name = (pm.background or {}).get("image")
    if not src_name:
        raise HTTPException(status_code=400, detail="Page has no raster to clean")

    doc_dir = os.path.join(DATA_DIR, "extracted_html", doc_id)

    if method == "inpaint":
        clean_name = src_name.rsplit(".", 1)[0] + ".clean-inpaint.png"
    else:
        clean_name = src_name.rsplit(".", 1)[0] + ".clean.png"
    clean_path = os.path.join(doc_dir, clean_name)

    if os.path.exists(clean_path) and not force:
        status = "cached"
    else:
        src_path = os.path.join(doc_dir, src_name)
        if method == "inpaint":
            boxes_px = []
            try:
                from PIL import Image as _Image
                rw, rh = _Image.open(src_path).size
                sx = rw / (pm.page_w or 1.0)
                sy = rh / (pm.page_h or 1.0)
                for b in pm.blocks:
                    l, t, w, h = b.bbox
                    boxes_px.append((l * sx, t * sy, w * sx, h * sy))
            except Exception:
                boxes_px = []
            ok = image_cleaner.clean_page_background_inpaint(src_path, clean_path, boxes_px)
        else:
            ok = image_cleaner.clean_page_background(src_path, clean_path)
        if not ok:
            raise HTTPException(status_code=502, detail="Background cleaning failed")
        status = "cleaned"

    pm.background["clean_image"] = clean_name
    page.model_json = pm.to_json()
    db.commit()
    return {"status": status, "clean_image": clean_name, "method": method}


@router.post("/api/docs/{doc_id}/pages/{page_num}/policy")
def set_page_policy(doc_id: str, page_num: int,
                    payload: PagePolicyRequest, db: Session = Depends(get_db)):
    from backend.app.services.page_model import PageModel
    page = db.query(DBPage).filter(DBPage.document_id == doc_id,
                                   DBPage.page_num == page_num).first()
    if not page or not page.model_json:
        raise HTTPException(status_code=404, detail="Page or model not found")
    pm = PageModel.from_json(page.model_json)
    val = payload.value
    if val == "auto":
        (pm.background or {}).pop("policy_override", None)
    elif val in ("base-color", "keep-raster", "clean-photo"):
        pm.background["policy_override"] = val
    else:
        raise HTTPException(status_code=400, detail="Invalid policy value")
    page.model_json = pm.to_json()
    db.commit()
    return {"policy_override": (pm.background or {}).get("policy_override")}


@router.post("/api/docs/{doc_id}/pages/{page_num}/clean-bg/revert")
def revert_clean_bg(doc_id: str, page_num: int, db: Session = Depends(get_db)):
    from backend.app.services.page_model import PageModel
    page = db.query(DBPage).filter(DBPage.document_id == doc_id,
                                   DBPage.page_num == page_num).first()
    if not page or not page.model_json:
        raise HTTPException(status_code=404, detail="Page or model not found")
    pm = PageModel.from_json(page.model_json)
    pm.background.pop("clean_image", None)
    page.model_json = pm.to_json()
    db.commit()
    return {"status": "reverted"}
