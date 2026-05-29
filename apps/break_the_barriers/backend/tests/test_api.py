import pytest
from fastapi.testclient import TestClient

def test_root_status(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"

def test_list_documents(client):
    response = client.get("/api/docs")
    assert response.status_code == 200
    docs = response.json()
    assert isinstance(docs, list)
    if len(docs) > 0:
        assert "id" in docs[0]
        assert "filename" in docs[0]
        assert "status" in docs[0]

def test_upload_document(client):
    # Upload a valid PDF file
    files = {"file": ("test_doc.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    response = client.post("/api/docs/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "test_doc.pdf"
    assert data["status"] == "raw"
    
    # Try to upload an invalid file extension (YAGNI/API safety check)
    files_invalid = {"file": ("test_doc.txt", b"plain text", "text/plain")}
    response_invalid = client.post("/api/docs/upload", files=files_invalid)
    assert response_invalid.status_code == 400
    assert "PDF or EPUB" in response_invalid.json()["detail"]

def test_upload_epub(client):
    files = {"file": ("my_book.epub", b"PK\x03\x04mock epub content", "application/epub+zip")}
    response = client.post("/api/docs/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "my_book.epub"
    assert data["status"] == "raw"


def test_upload_rejects_non_pdf_epub(client):
    files = {"file": ("notes.docx", b"PK mock docx", "application/vnd.openxmlformats")}
    response = client.post("/api/docs/upload", files=files)
    assert response.status_code == 400
    assert "PDF or EPUB" in response.json()["detail"]


def test_extract_epub_document(client):
    files = {"file": ("sample_book.epub", b"PK\x03\x04mock epub", "application/epub+zip")}
    client.post("/api/docs/upload", files=files)

    response = client.post("/api/docs/sample_book/extract")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "sample_book"
    assert data["pages_count"] > 0
    assert "extracted_html_dir" in data


def test_extract_document(client):
    # Success case
    response = client.post("/api/docs/clean_code/extract")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "clean_code"
    assert "extracted_html_dir" in data
    
    # 404 Case
    response_404 = client.post("/api/docs/invalid_id/extract")
    assert response_404.status_code == 404

def test_get_page_content(client):
    # Extract the document first to populate the pages/translations tables
    client.post("/api/docs/clean_code/extract")
    
    # Success case
    response = client.get("/api/docs/clean_code/pages/1?lang=en")
    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == "clean_code"
    assert data["page_num"] == 1
    assert data["lang"] == "en"
    assert "Hello World" in data["html"]
    
    # Vi translation query
    response_vi = client.get("/api/docs/clean_code/pages/1?lang=vi")
    assert response_vi.status_code == 200
    assert "Xin chào Thế giới" in response_vi.json()["html"]
    
    # 404 Case for invalid doc_id
    response_404_id = client.get("/api/docs/invalid_id/pages/1")
    assert response_404_id.status_code == 404
    
    # 404 Case for invalid page_num
    response_404_page = client.get("/api/docs/clean_code/pages/9999")
    assert response_404_page.status_code == 404

def test_translate_page(client):
    # Extract the document first to populate the pages/translations tables
    client.post("/api/docs/clean_code/extract")
    
    # Success case
    payload = {"page_num": 1, "target_lang": "vi"}
    response = client.post("/api/docs/clean_code/translate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "translated"
    assert data["page_num"] == 1
    
    # Invalid page number input
    payload_invalid = {"page_num": -5, "target_lang": "vi"}
    response_invalid = client.post("/api/docs/clean_code/translate", json=payload_invalid)
    assert response_invalid.status_code == 400

def test_compile_page(client):
    # Extract the document first to populate the pages/translations tables
    client.post("/api/docs/clean_code/extract")
    
    # Success case
    payload = {"page_num": 1}
    response = client.post("/api/docs/clean_code/compile", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "compiled"
    assert "html_path" in data
    
    # Invalid page number input
    payload_invalid = {"page_num": -1}
    response_invalid = client.post("/api/docs/clean_code/compile", json=payload_invalid)
    assert response_invalid.status_code == 400

def test_async_endpoints(client):
    # 1. Async Extract
    response = client.post("/api/docs/clean_code/extract?async_mode=true")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "extracting"
    assert data["doc_id"] == "clean_code"
    
    # 2. Async Translate
    payload_trans = {"page_num": 1, "target_lang": "vi"}
    response_trans = client.post("/api/docs/clean_code/translate?async_mode=true", json=payload_trans)
    assert response_trans.status_code == 202
    assert response_trans.json()["status"] == "translating"
    
    # 3. Async Compile
    payload_comp = {"page_num": 1}
    response_comp = client.post("/api/docs/clean_code/compile?async_mode=true", json=payload_comp)
    assert response_comp.status_code == 202
    assert response_comp.json()["status"] == "compiling"

def test_translation_memory_apis(client):
    # Extract first
    client.post("/api/docs/clean_code/extract")
    
    # 1. List translations
    response = client.get("/api/docs/clean_code/translations?limit=2&offset=0")
    assert response.status_code == 200
    translations = response.json()
    assert len(translations) <= 2
    assert "span_id" in translations[0]
    assert "original_text" in translations[0]
    
    # Translate first to have translated texts
    payload_trans = {"page_num": 1, "target_lang": "vi"}
    client.post("/api/docs/clean_code/translate", json=payload_trans)
    
    # Compile the page so we can test Put translation re-compilation
    payload_comp = {"page_num": 1}
    client.post("/api/docs/clean_code/compile", json=payload_comp)
    
    # 2. Search translations
    response_search = client.get("/api/docs/clean_code/translations/search?q=Introductory")
    assert response_search.status_code == 200
    search_results = response_search.json()
    assert len(search_results) > 0
    assert any("Introductory" in t["original_text"] for t in search_results)
    
    # 3. Update translation
    payload_update = {"translated_text": "Lập trình Nhập môn"}
    response_update = client.put("/api/docs/clean_code/translations/s1", json=payload_update)
    assert response_update.status_code == 200
    data_update = response_update.json()
    assert data_update["status"] == "updated"
    assert data_update["translated_text"] == "Lập trình Nhập môn"
    assert 1 in data_update["recompiled_pages"]

def test_delete_document(client):
    # Upload and get document info
    files = {"file": ("to_delete.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    client.post("/api/docs/upload", files=files)
    
    # Try deleting it
    response = client.delete("/api/docs/to_delete")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deleted"
    assert data["doc_id"] == "to_delete"
    
    # Check it is deleted from list
    response_list = client.get("/api/docs")
    docs = response_list.json()
    assert not any(d["id"] == "to_delete" for d in docs)

def test_get_document_pages(client):
    # Extract first
    client.post("/api/docs/clean_code/extract")

    # Success case
    response = client.get("/api/docs/clean_code/pages")
    assert response.status_code == 200
    pages = response.json()
    assert isinstance(pages, list)
    assert len(pages) > 0
    assert "page_num" in pages[0]
    assert "status" in pages[0]
    assert "has_original" in pages[0]
    assert "has_translated" in pages[0]

    # 404 Case
    response_404 = client.get("/api/docs/invalid_id/pages")
    assert response_404.status_code == 404

def test_get_volume_profile(client):
    response = client.get("/api/docs/clean_code/volume")
    assert response.status_code == 200
    data = response.json()
    assert "tier" in data
    assert "estimated_cost_usd" in data
    assert "processing_path" in data
    assert data["page_count"] == 10
    assert data["tier"] == "S"  # clean_code has 10 pages → S tier
    assert data["processing_path"] == "asyncio"
    assert data["recommended_quality"] == "high"

def test_get_volume_profile_not_found(client):
    response = client.get("/api/docs/nonexistent_doc/volume")
    assert response.status_code == 404

def test_get_volume_profile_quality_override(client):
    response_fast = client.get("/api/docs/clean_code/volume?quality_override=fast")
    response_high = client.get("/api/docs/clean_code/volume?quality_override=high")
    assert response_fast.status_code == 200
    assert response_high.status_code == 200
    data_fast = response_fast.json()
    data_high = response_high.json()
    # fast (1x multiplier) should have fewer tokens than high (3x multiplier)
    assert data_fast["estimated_tokens"] < data_high["estimated_tokens"]

def test_upload_auto_detects_volume(client):
    files = {"file": ("small_book.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    response = client.post("/api/docs/upload", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "small_book.pdf"
    assert data["status"] == "raw"
    # Upload should not fail due to volume detection
    # Verify the doc was created (volume detection happened silently)
    list_response = client.get("/api/docs")
    assert list_response.status_code == 200
    doc_ids = [d["id"] for d in list_response.json()]
    assert "small_book" in doc_ids


def test_translate_all_creates_jobs(client):
    # Extract first so pages exist
    client.post("/api/docs/clean_code/extract")

    response = client.post(
        "/api/docs/clean_code/translate-all",
        json={"target_lang": "vi", "quality_tier": "high"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert data["doc_id"] == "clean_code"
    assert data["total_pages"] == 10
    assert "job_ids" in data
    assert len(data["job_ids"]) == 10

def test_translate_all_doc_not_found(client):
    response = client.post(
        "/api/docs/nonexistent/translate-all",
        json={"target_lang": "vi"}
    )
    assert response.status_code == 404

def test_translate_all_jobs_visible_in_list(client):
    client.post("/api/docs/clean_code/extract")
    client.post("/api/docs/clean_code/translate-all", json={"target_lang": "vi"})

    response = client.get("/api/docs/clean_code/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) > 0
    assert all(j["stage"] == "translate" for j in jobs)

def test_get_job_status(client):
    # Setup: extract then translate-all to create jobs
    client.post("/api/docs/clean_code/extract")
    translate_resp = client.post(
        "/api/docs/clean_code/translate-all",
        json={"target_lang": "vi"}
    )
    job_ids = translate_resp.json()["job_ids"]
    assert len(job_ids) > 0

    job_id = job_ids[0]
    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id
    assert data["doc_id"] == "clean_code"
    assert data["stage"] == "translate"
    assert "status" in data
    assert "volume_tier" in data
    assert "quality_tier" in data

def test_get_job_status_not_found(client):
    response = client.get("/api/jobs/nonexistent-job-id")
    assert response.status_code == 404

def test_list_document_jobs_empty(client):
    # No jobs created yet — fresh test isolation from conftest
    response = client.get("/api/docs/clean_code/jobs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_list_document_jobs_after_translate_all(client):
    client.post("/api/docs/clean_code/extract")
    client.post("/api/docs/clean_code/translate-all", json={"target_lang": "vi"})

    response = client.get("/api/docs/clean_code/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 10  # 10 pages in clean_code
    for job in jobs:
        assert "id" in job
        assert "page_num" in job
        assert job["stage"] == "translate"

def test_list_document_jobs_filter_by_status(client):
    client.post("/api/docs/clean_code/extract")
    client.post("/api/docs/clean_code/translate-all", json={"target_lang": "vi"})

    # All jobs start as pending (or may be done if background ran sync in test)
    response = client.get("/api/docs/clean_code/jobs")
    assert response.status_code == 200
    jobs = response.json()
    # Filter by an actual status that should exist
    first_status = jobs[0]["status"]
    filtered = client.get(f"/api/docs/clean_code/jobs?status={first_status}")
    assert filtered.status_code == 200
    filtered_jobs = filtered.json()
    assert all(j["status"] == first_status for j in filtered_jobs)

def test_progress_stream_returns_sse(client, db_session):
    # Extract then compile all pages so the SSE generator can exit on its first
    # iteration (done == total > 0). We also patch the generator's SessionLocal
    # to use the same in-memory test DB so it sees the compiled pages, and patch
    # asyncio.sleep to a no-op so the generator does not sleep between iterations.
    from unittest.mock import patch, AsyncMock
    from tests.conftest import TestingSessionLocal

    client.post("/api/docs/clean_code/extract")
    for page_num in range(1, 11):
        client.post("/api/docs/clean_code/compile", json={"page_num": page_num})

    async def instant_sleep(_):
        pass

    with patch("backend.app.routers.jobs.SessionLocal", TestingSessionLocal), \
         patch("backend.app.routers.jobs.asyncio.sleep", instant_sleep):
        response = client.get("/api/docs/clean_code/progress")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "data:" in content
    import json as _json
    for line in content.splitlines():
        if line.startswith("data:"):
            data = _json.loads(line[5:].strip())
            assert "total" in data
            assert "percent" in data
            assert "status" in data
            break


def test_translate_all_sm_does_not_call_celery(client, monkeypatch, db_session):
    """S tier (10 pages = clean_code) must use asyncio path — Celery never called."""
    from backend.app.models_db import DBDocument

    # Set volume_tier explicitly so translate-all uses S (not the "M" fallback)
    doc = db_session.query(DBDocument).filter(DBDocument.id == "clean_code").first()
    doc.volume_tier = "S"
    db_session.commit()

    celery_calls = []

    def fake_celery(job_id, doc_id, page_num, target_lang, quality, tier):
        celery_calls.append(job_id)
        return "fake-task-id"

    monkeypatch.setattr(
        "backend.app.services.job_manager.dispatch_celery_job",
        fake_celery,
    )

    client.post("/api/docs/clean_code/extract")
    resp = client.post("/api/docs/clean_code/translate-all", json={"target_lang": "vi"})

    assert resp.status_code == 200
    assert resp.json()["volume_tier"] == "S"
    assert celery_calls == [], f"S tier must NOT use Celery, got: {celery_calls}"


def test_translate_all_lxl_calls_celery(client, monkeypatch, db_session):
    """XL tier must dispatch every page to Celery."""
    from backend.app.models_db import DBDocument, DBPage
    from backend.app.database import get_db
    from backend.app.main import app
    from fastapi.testclient import TestClient

    # Create XL document
    xl_doc = DBDocument(
        id="xl_book",
        filename="xl_book.pdf",
        total_pages=10,
        status="raw",
        volume_tier="XL",
        quality_tier="fast",
    )
    db_session.add(xl_doc)
    db_session.commit()

    celery_calls = []

    def fake_celery(job_id, doc_id, page_num, target_lang, quality, tier):
        celery_calls.append({"job_id": job_id, "tier": tier, "queue": "celery-low" if tier == "XL" else "celery-high"})
        return "fake-task-id"

    monkeypatch.setattr(
        "backend.app.services.job_manager.dispatch_celery_job",
        fake_celery,
    )

    def override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    c = TestClient(app)

    # Extract pages (mock creates pages for total_pages=10)
    c.post("/api/docs/xl_book/extract")

    resp = c.post("/api/docs/xl_book/translate-all", json={"target_lang": "vi", "quality_tier": "fast"})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["volume_tier"] == "XL"
    assert data["total_pages"] > 0
    assert len(celery_calls) == data["total_pages"], (
        f"Expected {data['total_pages']} Celery calls, got {len(celery_calls)}"
    )
    assert all(c["tier"] == "XL" for c in celery_calls)


def test_resume_document_not_found(client):
    response = client.post("/api/docs/nonexistent/resume")
    assert response.status_code == 404

def test_resume_document_returns_ok(client):
    """Resume on any document returns 200 with correct fields."""
    response = client.post("/api/docs/clean_code/resume")
    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == "clean_code"
    assert "queued" in data
    assert "status" in data
    assert "detail" in data

def test_resume_requeues_extracted_pages(client, db_session):
    """Pages with status 'extracted' must be re-queued for translation."""
    from backend.app.models_db import DBPage
    from backend.app.database import get_db
    from backend.app.main import app
    from fastapi.testclient import TestClient

    def override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    c = TestClient(app)

    # Extract to create pages
    c.post("/api/docs/clean_code/extract")

    # Manually set page 1 to 'extracted' to simulate interrupted translation
    page = db_session.query(DBPage).filter(
        DBPage.document_id == "clean_code", DBPage.page_num == 1
    ).first()
    if page:
        page.status = "extracted"
        db_session.commit()

    resp = c.post("/api/docs/clean_code/resume")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] > 0
    assert data["detail"]["pages_re_translated"] > 0

def test_resume_marks_stuck_jobs_failed(client, db_session):
    """Jobs running > 30 min must be marked failed on resume."""
    from backend.app.models_db import DBJob
    from datetime import datetime, timezone, timedelta
    from backend.app.database import get_db
    from backend.app.main import app
    from fastapi.testclient import TestClient

    stuck_job = DBJob(
        doc_id="clean_code",
        page_num=1,
        stage="translate",
        status="running",
        volume_tier="S",
        quality_tier="high",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=45),
    )
    db_session.add(stuck_job)
    db_session.commit()
    db_session.refresh(stuck_job)
    job_id = stuck_job.id

    def override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    c = TestClient(app)
    c.post("/api/docs/clean_code/resume")
    app.dependency_overrides.clear()

    db_session.expire_all()
    updated = db_session.query(DBJob).filter(DBJob.id == job_id).first()
    assert updated.status == "failed"
    assert "timeout" in (updated.error_msg or "").lower()


# -------------------------------------------------------------
# Auth Tests (SP2)
# -------------------------------------------------------------

def test_register_user(client):
    response = client.post("/api/auth/register", json={
        "email": "newuser@example.com",
        "password": "testpass123",
        "full_name": "Test User"
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["plan"] == "free"
    assert data["user"]["pages_limit"] == 20


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "pass123456", "full_name": "A"}
    client.post("/api/auth/register", json=payload)
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


def test_login_user(client):
    client.post("/api/auth/register", json={
        "email": "login@example.com", "password": "mypassword123", "full_name": "Login User"
    })
    response = client.post("/api/auth/login", json={
        "email": "login@example.com", "password": "mypassword123"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={
        "email": "wp@example.com", "password": "correctpass123", "full_name": "WP"
    })
    response = client.post("/api/auth/login", json={
        "email": "wp@example.com", "password": "wrongpassword"
    })
    assert response.status_code == 401


def test_get_me(client):
    reg = client.post("/api/auth/register", json={
        "email": "me@example.com", "password": "pass123456", "full_name": "Me"
    })
    token = reg.json()["access_token"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_get_me_no_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_upload_with_auth_sets_user_id(client, db_session):
    from backend.app.models_db import DBDocument
    reg = client.post("/api/auth/register", json={
        "email": "uploader@example.com", "password": "pass123456", "full_name": "U"
    })
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]
    files = {"file": ("auth_book.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    resp = client.post("/api/docs/upload", files=files,
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    doc = db_session.query(DBDocument).filter_by(id="auth_book").first()
    assert doc is not None
    assert doc.user_id == user_id
    from backend.app.models_db import DBUser
    user_obj = db_session.query(DBUser).filter_by(id=user_id).first()
    db_session.refresh(user_obj)
    assert user_obj.pages_used_this_month > 0


def test_upload_without_auth_still_works(client):
    files = {"file": ("noauth_book.pdf", b"%PDF-1.4 mock", "application/pdf")}
    resp = client.post("/api/docs/upload", files=files)
    assert resp.status_code == 200


def test_quota_exceeded(client, db_session):
    from backend.app.models_db import DBUser
    reg = client.post("/api/auth/register", json={
        "email": "quota@example.com", "password": "pass123456", "full_name": "Q"
    })
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    user = db_session.query(DBUser).filter_by(email="quota@example.com").first()
    user.pages_used_this_month = user.pages_limit  # free = 20, fill it up
    db_session.commit()
    files = {"file": ("over_quota.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    resp = client.post("/api/docs/upload", files=files,
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 402
    assert "Quota" in resp.json()["detail"]
