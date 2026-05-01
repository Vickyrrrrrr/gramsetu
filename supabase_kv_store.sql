-- ============================================================
-- GramSetu v3 - Persistent State Migration
-- Run this script in your Supabase SQL Editor to create the 
-- kv_store table for persistent rate limits, user identity hashing, 
-- and data vault.
-- ============================================================

CREATE TABLE IF NOT EXISTS kv_store (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB,
    expires_at DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    PRIMARY KEY (namespace, key)
);

-- Index to optimize querying expired items quickly
CREATE INDEX IF NOT EXISTS idx_kv_store_expires_at ON kv_store(expires_at);

-- Set up Row Level Security (RLS) defaults
ALTER TABLE kv_store ENABLE ROW LEVEL SECURITY;

-- If connecting via a Service Role Key from the backend, 
-- explicit policies aren't strictly required (the service key bypasses RLS),
-- but here receives a blanket rule just in case.
CREATE POLICY "Enable all operations for service role" ON kv_store
    AS PERMISSIVE FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
