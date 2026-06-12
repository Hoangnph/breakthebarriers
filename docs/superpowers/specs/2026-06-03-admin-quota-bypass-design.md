# Admin Quota Bypass (dev)

**Ngày:** 2026-06-03
**App:** `apps/break_the_barriers`
**Trạng thái:** Design — chờ duyệt trước khi lập plan.

---

## 1. Bối cảnh & vấn đề

Upload bị chặn bởi quota: `app/routers/documents.py` (~dòng 101-108) khóa hàng user và raise HTTP 402 khi `pages_used_this_month + estimated_pages > pages_limit` (mặc định limit = 20). Khi phát triển, tài khoản admin (`admin@admin.com`) liên tục đụng giới hạn. Codebase **chưa có khái niệm admin**: `DBUser` chỉ có `email`, `plan`, `pages_used_this_month`, `pages_limit`.

## 2. Mục tiêu & phi-mục tiêu

**Mục tiêu:** Tài khoản có cờ `is_admin=true` được **bỏ qua quota** khi upload (không bị 402) và **không bị tính usage**.

**Phi-mục tiêu:**
- Không thêm endpoint/CLI để set cờ (set bằng SQL thủ công).
- Không phơi `is_admin` ra API (chưa cần).
- Không đổi JWT/login (quota check đã đọc user tươi từ DB).

**Tiêu chí thành công:**
- Admin upload vượt `pages_limit` → **không 402**; `pages_used_this_month` **không tăng**.
- Non-admin vượt limit → **vẫn 402** (không hồi quy).
- User mới: `is_admin` mặc định `False`.

## 3. Thiết kế

### 3.1 Model — `app/services/.../models_db.py` (`DBUser`)
Thêm cột:
```python
is_admin = Column(Boolean, default=False, nullable=False)
```
(`Boolean` import từ sqlalchemy nếu chưa có.)

### 3.2 Quota check — `app/routers/documents.py`
Trong khối quota của endpoint upload: chỉ enforce khi user **không** phải admin. Logic:
- Lấy `locked_user` (đã có, `with_for_update`).
- Nếu `locked_user and not locked_user.is_admin`:
  - Check `pages_used + estimated > pages_limit` → 402 (như cũ).
  - Sau khi tạo/cập nhật doc: `current_user.pages_used_this_month += estimated_pages` (như cũ).
- Nếu `locked_user.is_admin`: **bỏ qua cả check lẫn increment**.

Cách gọn: bọc check bằng `if locked_user and not locked_user.is_admin:` và bọc increment bằng `if current_user is not None and not current_user.is_admin:`.

### 3.3 Bật cờ (thủ công, một lần)
- Postgres: `ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;` rồi `UPDATE users SET is_admin=true WHERE email='admin@admin.com';`
- SQLite (test): tự tạo qua `create_all`.

## 4. Xử lý lỗi / degrade
- `current_user is None` (upload ẩn danh, nếu cho phép): giữ nguyên hành vi hiện tại (không quota).
- Cột thiếu ở DB cũ → cần ALTER (mục 3.3); SQLAlchemy model có default nên row mới ổn.

## 5. Testing
- **test_admin_bypasses_quota:** tạo user `is_admin=True`, `pages_limit=1`, upload tài liệu nhiều trang → status 200, `pages_used_this_month == 0` (không tăng).
- **test_nonadmin_still_blocked:** user thường `pages_limit=1`, upload vượt → 402 (regression).
- **test_new_user_is_admin_defaults_false:** user mới có `is_admin == False`.
- Dùng SQLite in-memory + fixture sẵn có; upload qua TestClient như các test API hiện tại.

## 6. Phạm vi
- Chạm: `models_db.py` (1 cột) + `documents.py` (2 chỗ bọc điều kiện) + test.
- Chỗ enforce quota duy nhất là upload nên không có điểm khác cần sửa.
