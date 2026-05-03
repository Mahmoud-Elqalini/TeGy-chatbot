-- Run order: core.sql → sessions.sql → messages.sql → session_memory.sql → conv_summaries.sql

-- ==========================================
-- 6. CONVERSATION SUMMARIES
-- ==========================================
CREATE TABLE conv_summaries (
    summarize_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL,
    summary      TEXT NOT NULL,
    version      INT NOT NULL DEFAULT 1,
    time         TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_summary_version UNIQUE (session_id, version),

    FOREIGN KEY (session_id)
        REFERENCES sessions(session_id)
        ON DELETE CASCADE
);

-- ==========================================
-- INDEXES
-- ==========================================
CREATE INDEX idx_summaries_session
    ON conv_summaries(session_id);