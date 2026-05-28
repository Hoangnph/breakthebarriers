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
    assert "Only PDF files are supported" in response_invalid.json()["detail"]

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
