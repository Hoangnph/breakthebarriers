import pytest
from backend.app.models_db import DBDocument, DBDocumentGlossary


@pytest.fixture
def doc_with_glossary(db_session, client):
    doc = DBDocument(id="glos-doc", filename="glos.pdf", total_pages=1, status="extracted")
    db_session.add(doc)
    entry = DBDocumentGlossary(
        document_id="glos-doc", source_term="Đạo", target_term="Tao", target_lang="en"
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


def test_get_glossary(client, doc_with_glossary):
    res = client.get("/api/docs/glos-doc/glossary?lang=en")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["entries"][0]["source_term"] == "Đạo"


def test_add_glossary_entry(client, db_session):
    doc = DBDocument(id="add-doc", filename="add.pdf", total_pages=1, status="extracted")
    db_session.add(doc)
    db_session.commit()
    res = client.post("/api/docs/add-doc/glossary", json={
        "source_term": "Vô vi", "target_term": "Wu Wei", "target_lang": "en", "is_manual": True
    })
    assert res.status_code == 201
    assert res.json()["source_term"] == "Vô vi"
    assert res.json()["is_manual"] is True


def test_update_glossary_entry(client, doc_with_glossary):
    entry_id = doc_with_glossary.id
    res = client.put(f"/api/docs/glos-doc/glossary/{entry_id}", json={"target_term": "The Way"})
    assert res.status_code == 200
    assert res.json()["target_term"] == "The Way"


def test_delete_glossary_entry(client, doc_with_glossary):
    entry_id = doc_with_glossary.id
    res = client.delete(f"/api/docs/glos-doc/glossary/{entry_id}")
    assert res.status_code == 200
    res2 = client.get("/api/docs/glos-doc/glossary?lang=en")
    assert res2.json()["total"] == 0


def test_get_glossary_404(client):
    res = client.get("/api/docs/no-such-doc/glossary")
    assert res.status_code == 404
