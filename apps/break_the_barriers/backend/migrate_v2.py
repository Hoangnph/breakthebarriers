"""
Migration v2: Add volume/quality columns to documents; create jobs table.
Run: .venv/bin/python migrate_v2.py
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/break_the_barriers")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
    ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS volume_tier VARCHAR DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS quality_tier VARCHAR DEFAULT 'high',
    ADD COLUMN IF NOT EXISTS estimated_cost_usd FLOAT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS estimated_duration_min INT DEFAULT NULL;
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id VARCHAR PRIMARY KEY,
        doc_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        page_num INT DEFAULT NULL,
        stage VARCHAR NOT NULL,
        status VARCHAR NOT NULL DEFAULT 'pending',
        volume_tier VARCHAR NOT NULL,
        quality_tier VARCHAR NOT NULL DEFAULT 'high',
        retries INT DEFAULT 0,
        error_msg TEXT DEFAULT NULL,
        celery_task_id VARCHAR DEFAULT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        started_at TIMESTAMP DEFAULT NULL,
        completed_at TIMESTAMP DEFAULT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_doc_id ON jobs(doc_id);
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
""")

conn.commit()
cur.close()
conn.close()
print("Migration v2 complete.")
