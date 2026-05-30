-- SP3 Web-Book Publisher migration
-- Run against the PostgreSQL break_the_barriers database.

CREATE TABLE IF NOT EXISTS published_books (
    id           VARCHAR PRIMARY KEY,
    document_id  VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id      VARCHAR REFERENCES users(id) ON DELETE SET NULL,
    slug         VARCHAR UNIQUE NOT NULL,
    title        VARCHAR NOT NULL,
    description  TEXT    DEFAULT '',
    cover_url    VARCHAR,
    cover_path   VARCHAR,
    languages    TEXT    DEFAULT '["vi"]',
    is_public    BOOLEAN DEFAULT TRUE,
    published_at TIMESTAMP DEFAULT NOW(),
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_published_books_slug ON published_books(slug);
CREATE INDEX IF NOT EXISTS idx_published_books_document_id ON published_books(document_id);
