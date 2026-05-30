import json
import pytest
from backend.app.models_db import DBPublishedBook, DBDocument, DBPage, DBUser
from backend.app.services.auth_service import create_access_token, hash_password


def test_published_book_model_columns():
    """DBPublishedBook has the expected columns."""
    cols = DBPublishedBook.__table__.columns.keys()
    for expected in ["id", "document_id", "user_id", "slug", "title",
                     "description", "cover_url", "cover_path", "languages",
                     "is_public", "published_at", "created_at"]:
        assert expected in cols, f"missing column {expected}"


def test_pydantic_book_models_importable():
    from backend.app.models import PublishRequest, BookInfo, BookPageInfo, BookPageContent
    req = PublishRequest(slug="my-book", title="My Book")
    assert req.languages == ["vi"]
    assert req.is_public is True


@pytest.fixture
def auth_user(db_session):
    """Create a user and return (user, auth_headers)."""
    user = DBUser(email="pub@test.com", hashed_password=hash_password("secret1"), full_name="Pub")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id, user.email, user.plan)
    return user, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def translated_doc(db_session, auth_user):
    """A document owned by auth_user, status=translated, with 2 pages."""
    user, _ = auth_user
    doc = DBDocument(id="doc-trans", filename="Book.pdf", total_pages=2,
                     status="translated", user_id=user.id)
    db_session.add(doc)
    db_session.add(DBPage(document_id="doc-trans", page_num=1,
                          original_html="<p>Hello</p>", translated_html="<p>Xin chào</p>",
                          status="translated"))
    db_session.add(DBPage(document_id="doc-trans", page_num=2,
                          original_html="<p>World</p>", translated_html="<p>Thế giới</p>",
                          status="translated"))
    db_session.commit()
    return doc


def test_publish_book(client, auth_user, translated_doc):
    _, headers = auth_user
    res = client.post("/api/docs/doc-trans/publish",
                      data={"slug": "test-book", "title": "Test Book",
                            "languages": '["vi","en"]', "is_public": "true"},
                      headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["slug"] == "test-book"
    assert body["book_url"] == "/read/test-book"


def test_publish_invalid_slug(client, auth_user, translated_doc):
    _, headers = auth_user
    res = client.post("/api/docs/doc-trans/publish",
                      data={"slug": "AB", "title": "T", "languages": '["vi"]'},
                      headers=headers)
    assert res.status_code == 422


def test_publish_duplicate_slug(client, auth_user, translated_doc):
    _, headers = auth_user
    client.post("/api/docs/doc-trans/publish",
                data={"slug": "dup-slug", "title": "T", "languages": '["vi"]'},
                headers=headers)
    res = client.post("/api/docs/doc-trans/publish",
                      data={"slug": "dup-slug", "title": "T2", "languages": '["vi"]'},
                      headers=headers)
    assert res.status_code == 409


def test_publish_wrong_status(client, auth_user):
    user, headers = auth_user
    res = client.post("/api/docs/clean_code/publish",
                      data={"slug": "raw-book", "title": "T", "languages": '["vi"]'},
                      headers=headers)
    # clean_code is status=raw and not owned by this user
    assert res.status_code in (403, 422)


def test_publish_requires_auth(client, translated_doc):
    res = client.post("/api/docs/doc-trans/publish",
                      data={"slug": "noauth", "title": "T", "languages": '["vi"]'})
    assert res.status_code == 401


@pytest.fixture
def published_book(client, auth_user, translated_doc):
    """Publish translated_doc and return its slug."""
    _, headers = auth_user
    client.post("/api/docs/doc-trans/publish",
                data={"slug": "pub-book", "title": "Pub Book",
                      "description": "A description",
                      "languages": '["vi","en"]', "is_public": "true"},
                headers=headers)
    return "pub-book"


@pytest.fixture
def private_book(client, auth_user, db_session):
    """Publish a private book owned by auth_user."""
    user, headers = auth_user
    doc = DBDocument(id="doc-priv", filename="Priv.pdf", total_pages=1,
                     status="translated", user_id=user.id)
    db_session.add(doc)
    db_session.add(DBPage(document_id="doc-priv", page_num=1,
                          original_html="<p>secret</p>", translated_html="<p>bí mật</p>",
                          status="translated"))
    db_session.commit()
    client.post("/api/docs/doc-priv/publish",
                data={"slug": "priv-book", "title": "Priv", "languages": '["vi"]',
                      "is_public": "false"},
                headers=headers)
    return "priv-book"


def test_get_public_book(client, published_book):
    res = client.get(f"/api/books/{published_book}")
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Pub Book"
    assert body["page_count"] == 2
    assert body["languages"] == ["vi", "en"]
    assert body["book_url"] == "/read/pub-book"


def test_get_book_404(client):
    res = client.get("/api/books/does-not-exist")
    assert res.status_code == 404


def test_get_book_pages(client, published_book):
    res = client.get(f"/api/books/{published_book}/pages")
    assert res.status_code == 200
    pages = res.json()
    assert len(pages) == 2
    assert pages[0]["page_number"] == 1
    assert "preview" in pages[0]


def test_get_page_content_vi(client, published_book):
    res = client.get(f"/api/books/{published_book}/pages/1?lang=vi")
    assert res.status_code == 200
    body = res.json()
    assert body["lang"] == "vi"
    assert "Xin chào" in body["html"]
    assert body["prev_page"] is None
    assert body["next_page"] == 2
    assert body["total_pages"] == 2


def test_get_page_content_en(client, published_book):
    res = client.get(f"/api/books/{published_book}/pages/2?lang=en")
    assert res.status_code == 200
    body = res.json()
    assert body["lang"] == "en"
    assert "World" in body["html"]
    assert body["prev_page"] == 1
    assert body["next_page"] is None


def test_get_page_lang_not_published(client, published_book):
    res = client.get(f"/api/books/{published_book}/pages/1?lang=zh")
    assert res.status_code == 400


def test_get_page_out_of_range(client, published_book):
    res = client.get(f"/api/books/{published_book}/pages/99?lang=vi")
    assert res.status_code == 404


def test_private_book_unauthorized(client, private_book):
    res = client.get(f"/api/books/{private_book}")
    assert res.status_code == 403


def test_private_book_owner_can_read(client, auth_user, private_book):
    _, headers = auth_user
    res = client.get(f"/api/books/{private_book}", headers=headers)
    assert res.status_code == 200


def test_private_book_pages_unauthorized(client, private_book):
    res = client.get(f"/api/books/{private_book}/pages")
    assert res.status_code == 403


def test_private_book_page_content_unauthorized(client, private_book):
    res = client.get(f"/api/books/{private_book}/pages/1?lang=vi")
    assert res.status_code == 403


def test_unpublish(client, auth_user, published_book):
    _, headers = auth_user
    res = client.delete(f"/api/books/{published_book}", headers=headers)
    assert res.status_code == 200
    res2 = client.get(f"/api/books/{published_book}")
    assert res2.status_code == 404


def test_unpublish_requires_owner(client, published_book, db_session):
    other = DBUser(email="other@test.com", hashed_password=hash_password("secret1"))
    db_session.add(other)
    db_session.commit()
    token = create_access_token(other.id, other.email, other.plan)
    res = client.delete(f"/api/books/{published_book}",
                        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_unpublish_requires_auth(client, published_book):
    res = client.delete(f"/api/books/{published_book}")
    assert res.status_code == 401
