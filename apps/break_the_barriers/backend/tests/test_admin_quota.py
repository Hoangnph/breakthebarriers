def test_new_user_is_admin_defaults_false(client, db_session):
    from backend.app.models_db import DBUser
    reg = client.post("/api/auth/register", json={
        "email": "plainuser@example.com", "password": "pass123456", "full_name": "P"})
    assert reg.status_code == 201
    uid = reg.json()["user"]["id"]
    u = db_session.query(DBUser).filter_by(id=uid).first()
    assert u.is_admin is False


def test_admin_bypasses_quota(client, db_session):
    from backend.app.models_db import DBUser
    reg = client.post("/api/auth/register", json={
        "email": "admin@admin.com", "password": "pass123456", "full_name": "A"})
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    uid = reg.json()["user"]["id"]
    u = db_session.query(DBUser).filter_by(id=uid).first()
    u.is_admin = True
    u.pages_limit = 1
    db_session.commit()
    files = {"file": ("admin_book.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    resp = client.post("/api/docs/upload", files=files,
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    db_session.refresh(u)
    assert u.pages_used_this_month == 0


def test_nonadmin_blocked_by_quota(client, db_session):
    from backend.app.models_db import DBUser
    reg = client.post("/api/auth/register", json={
        "email": "limited@example.com", "password": "pass123456", "full_name": "L"})
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    uid = reg.json()["user"]["id"]
    u = db_session.query(DBUser).filter_by(id=uid).first()
    u.pages_limit = 1
    db_session.commit()
    files = {"file": ("limited_book.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    resp = client.post("/api/docs/upload", files=files,
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 402
