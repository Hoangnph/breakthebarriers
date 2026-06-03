def test_new_user_is_admin_defaults_false(client, db_session):
    from backend.app.models_db import DBUser
    reg = client.post("/api/auth/register", json={
        "email": "plainuser@example.com", "password": "pass123456", "full_name": "P"})
    assert reg.status_code == 201
    uid = reg.json()["user"]["id"]
    u = db_session.query(DBUser).filter_by(id=uid).first()
    assert u.is_admin is False
