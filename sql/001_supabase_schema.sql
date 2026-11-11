-- ============================================================================
-- OMNI DUAL-BRAIN: SUPABASE HYBRID DATABASE SCHEMA (RELATIONAL + PGVECTOR)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Snapshots Diários de Métricas (GitHub, Farcaster/Neynar, KarmaHQ)
CREATE TABLE IF NOT EXISTS ecosystem_metric_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(32) NOT NULL CHECK (source IN ('github', 'neynar', 'karmahq')),
    project_slug VARCHAR(128) NOT NULL,
    commits_count INTEGER DEFAULT 0,
    stars_count INTEGER DEFAULT 0,
    open_prs_count INTEGER DEFAULT 0,
    farcaster_likes INTEGER DEFAULT 0,
    farcaster_recasts INTEGER DEFAULT 0,
    farcaster_followers INTEGER DEFAULT 0,
    karmahq_milestones_completed INTEGER DEFAULT 0,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_metrics_source_date
    ON ecosystem_metric_snapshots (source, recorded_at DESC);

-- 2. Base de Conhecimento Híbrida (Graphify + RAG Vetorial)
CREATE TABLE IF NOT EXISTS knowledge_graph_nodes (
    node_id VARCHAR(128) PRIMARY KEY,
    node_type VARCHAR(32) NOT NULL CHECK (node_type IN ('doc', 'code_symbol', 'tutorial', 'whitepaper', 'spec')),
    title TEXT NOT NULL,
    file_path TEXT,
    content TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    outbound_links TEXT[] DEFAULT '{}',
    embedding vector(1536),
    last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Auditoria de Segurança e Aprovações Human-in-the-Loop (HITL)
CREATE TABLE IF NOT EXISTS security_hitl_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id VARCHAR(128) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    channel VARCHAR(32) NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('public', 'admin')),
    action_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('blocked', 'pending_approval', 'approved', 'rejected', 'executed')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
