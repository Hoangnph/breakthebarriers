-- Faithful SVG reader: thêm cột artifact cho bảng pages (prod Postgres).
-- SQLite test tự tạo từ model nên không cần chạy ở test.
ALTER TABLE pages ADD COLUMN IF NOT EXISTS svg_path TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS text_layer_json TEXT;
