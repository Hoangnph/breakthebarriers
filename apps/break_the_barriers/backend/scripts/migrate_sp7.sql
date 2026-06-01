-- SP7 TranslatorV2 Migration
-- Run against: postgresql://postgres:postgres@localhost:5432/break_the_barriers

ALTER TABLE documents ADD COLUMN IF NOT EXISTS ai_metadata TEXT DEFAULT '{}';

ALTER TABLE pages ADD COLUMN IF NOT EXISTS needs_review        BOOLEAN DEFAULT FALSE;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS review_reason       TEXT;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS translation_quality FLOAT;

CREATE TABLE IF NOT EXISTS document_glossaries (
    id          VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    target_lang VARCHAR(10) NOT NULL,
    is_manual   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (document_id, source_term, target_lang)
);
CREATE INDEX IF NOT EXISTS idx_glossaries_doc_lang ON document_glossaries(document_id, target_lang);

CREATE TABLE IF NOT EXISTS translation_memory (
    source_hash VARCHAR(64) PRIMARY KEY,
    source_text TEXT NOT NULL,
    target_lang VARCHAR(10) NOT NULL,
    translated  TEXT NOT NULL,
    quality     FLOAT DEFAULT 1.0,
    hit_count   INT DEFAULT 0,
    last_used   TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tm_lang ON translation_memory(target_lang);
