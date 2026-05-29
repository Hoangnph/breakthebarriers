-- SP2 Migration: users, subscriptions tables + documents columns
-- Run against existing PostgreSQL DB:
--   psql -d break_the_barriers -f migrate_sp2.sql

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    full_name VARCHAR DEFAULT '',
    plan VARCHAR DEFAULT 'free',
    pages_used_this_month INTEGER DEFAULT 0,
    pages_limit INTEGER DEFAULT 20,
    pages_reset_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS subscriptions (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR UNIQUE,
    status VARCHAR DEFAULT 'active',
    current_period_end TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id VARCHAR REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE;
