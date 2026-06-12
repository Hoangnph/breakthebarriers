-- Faithful Overlay Translation migration
-- Run against: postgresql://postgres:postgres@localhost:5432/break_the_barriers
ALTER TABLE pages ADD COLUMN IF NOT EXISTS layout_json TEXT;
