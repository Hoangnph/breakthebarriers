# Admin Quota Bypass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let accounts flagged `is_admin=True` upload without hitting the monthly page quota (no 402) and without metering usage.

**Architecture:** Add a boolean `is_admin` column to `DBUser`; in the upload endpoint, skip both the quota 402 check and the `pages_used_this_month` increment when the user is an admin. The flag is set manually via SQL.

**Tech Stack:** FastAPI, SQLAlchemy, pytest. Paths relative to `apps/break_the_barriers/backend/`. Git root: `/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator`.

---

## File Structure

| File | Responsibility | New? |
|---|---|---|
| `app/models_db.py` | Add `DBUser.is_admin` column | Modify |
| `app/routers/documents.py` | Gate quota check + increment on `not is_admin` | Modify |
| `tests/test_admin_quota.py` | Unit tests | Create |

---

## Task 1: Add `DBUser.is_admin` column

**Files:**
- Modify: `app/models_db.py` (DBUser, after `is_active`)
- Test: `tests/test_admin_quota.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_quota.py
def test_new_user_is_admin_defaults_false(client, db_session):
    from backend.app.models_db import DBUser
    reg = client.post("/api/auth/register", json={
        "email": "plainuser@example.com", "password": "pass123456", "full_name": "P"})
    assert reg.status_code == 201
    uid = reg.json()["user"]["id"]
    u = db_session.query(DBUser).filter_by(id=uid).first()
    assert u.is_admin is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_admin_quota.py::test_new_user_is_admin_defaults_false -v`
Expected: FAIL with `AttributeError: ... 'DBUser' ... has no attribute 'is_admin'` (or column missing).

- [ ] **Step 3: Add the column**

In `app/models_db.py`, in `DBUser`, add right after the `is_active = Column(Boolean, default=True)` line:

```python
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False, nullable=False)
```

(`Boolean` is already imported at the top of the file.)

> **Production note (Postgres):** the SQLite test DB is created via `create_all`, so the test passes immediately. The production Postgres DB needs the column added once:
> `ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;`
> Then flag the admin: `UPDATE users SET is_admin=true WHERE email='admin@admin.com';`

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_admin_quota.py::test_new_user_is_admin_defaults_false -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/models_db.py apps/break_the_barriers/backend/tests/test_admin_quota.py
git commit -m "feat: add DBUser.is_admin column

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Bypass quota for admins in upload

**Files:**
- Modify: `app/routers/documents.py` (quota check ~lines 101-109, increment ~lines 143-144)
- Test: `tests/test_admin_quota.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_admin_quota.py`:

```python
def test_admin_bypasses_quota(client, db_session):
    from backend.app.models_db import DBUser
    reg = client.post("/api/auth/register", json={
        "email": "admin@admin.com", "password": "pass123456", "full_name": "A"})
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    uid = reg.json()["user"]["id"]
    # Make this user an admin with a tiny limit.
    u = db_session.query(DBUser).filter_by(id=uid).first()
    u.is_admin = True
    u.pages_limit = 1
    db_session.commit()
    # Mock PDF has no /Count -> estimated 10 pages, well over the limit of 1.
    files = {"file": ("admin_book.pdf", b"%PDF-1.4 mock content", "application/pdf")}
    resp = client.post("/api/docs/upload", files=files,
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200            # not blocked
    db_session.refresh(u)
    assert u.pages_used_this_month == 0       # usage not metered for admin


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
    assert resp.status_code == 402            # still blocked
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_admin_quota.py -v`
Expected: `test_admin_bypasses_quota` FAILS (admin still gets 402 / usage incremented); `test_nonadmin_blocked_by_quota` already PASSES.

- [ ] **Step 3: Gate the quota check**

In `app/routers/documents.py`, the current quota check is:

```python
    if current_user is not None:
        locked_user = db.query(DBUser).filter(DBUser.id == current_user.id).with_for_update().first()
        if locked_user and locked_user.pages_used_this_month + estimated_pages > locked_user.pages_limit:
            raise HTTPException(
                status_code=402,
                detail=f"Quota exceeded ({locked_user.pages_used_this_month}/{locked_user.pages_limit} pages used). Please upgrade your plan."
            )
        current_user = locked_user  # use the freshly locked instance
```

Change the `if locked_user and ...` condition to skip admins:

```python
        if (locked_user and not locked_user.is_admin
                and locked_user.pages_used_this_month + estimated_pages > locked_user.pages_limit):
            raise HTTPException(
                status_code=402,
                detail=f"Quota exceeded ({locked_user.pages_used_this_month}/{locked_user.pages_limit} pages used). Please upgrade your plan."
            )
```

- [ ] **Step 4: Gate the increment**

The current increment is:

```python
    # Increment quota in the same transaction
    if current_user is not None:
        current_user.pages_used_this_month += estimated_pages
```

Change it to skip admins:

```python
    # Increment quota in the same transaction (admins are not metered)
    if current_user is not None and not current_user.is_admin:
        current_user.pages_used_this_month += estimated_pages
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_admin_quota.py -v`
Expected: all 3 PASS.

- [ ] **Step 6: Regression — existing upload/auth tests**

Run: `.venv/bin/pytest tests/test_api.py -q`
Expected: all pass (incl. `test_upload_with_auth_sets_user_id` — non-admin still metered).

- [ ] **Step 7: Commit**

```bash
cd /Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator
git add apps/break_the_barriers/backend/app/routers/documents.py apps/break_the_barriers/backend/tests/test_admin_quota.py
git commit -m "feat: bypass upload quota for admin accounts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review notes

- **Spec coverage:** is_admin column §3.1 → Task 1; quota check + increment gating §3.2 → Task 2 (Steps 3-4); manual SQL enablement §3.3 → Task 1 production note; tests §5 (admin bypass, non-admin 402, default False) → Tasks 1-2. Degrade (`current_user is None`) §4 → unchanged code paths preserved.
- **Placeholder scan:** none — all steps have complete code.
- **Type consistency:** `is_admin` (Boolean, default False) defined Task 1, read as `locked_user.is_admin` / `current_user.is_admin` in Task 2. Test mock PDF `b"%PDF-1.4 mock content"` → 10 estimated pages (no `/Count`), consistent with `pages_limit=1` to trigger/​bypass.
- **Production note:** Postgres needs the `ALTER TABLE` + `UPDATE` (Task 1 note); tests use SQLite `create_all`.
```
