-- Run order: core.sql → sessions.sql → messages.sql → session_memory.sql → conv_summaries.sql

-- ==========================================
-- 5. SESSION MEMORY
-- ==========================================
CREATE TABLE session_memory (
    memory_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL,
    memory_type  VARCHAR(50),
    content      TEXT NOT NULL,
    importance   FLOAT DEFAULT 0.5
        CHECK (importance BETWEEN 0.0 AND 1.0),
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),

    FOREIGN KEY (session_id)
        REFERENCES sessions(session_id)
        ON DELETE CASCADE
);

-- ==========================================
-- INDEXES
-- ==========================================
CREATE INDEX idx_memory_session
    ON session_memory(session_id);

-- ==========================================
-- TRIGGERS
-- ==========================================

-- Update updated_at for session_memory
CREATE OR REPLACE FUNCTION update_memory_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_memory_updated_at
BEFORE UPDATE ON session_memory
FOR EACH ROW
EXECUTE FUNCTION update_memory_updated_at();