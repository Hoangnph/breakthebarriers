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
