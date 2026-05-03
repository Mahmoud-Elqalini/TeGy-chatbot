-- Run order: core.sql → sessions.sql → messages.sql → session_memory.sql → conv_summaries.sql

-- ==========================================
-- 4. MESSAGES
-- ==========================================
CREATE TABLE messages (
    message_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL,
    role         VARCHAR(20) NOT NULL
        CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content      TEXT NOT NULL,
    token_count  INT DEFAULT 0,
    is_deleted   BOOLEAN DEFAULT FALSE,
    metadata     JSONB,
    sending_time TIMESTAMPTZ DEFAULT NOW(),

    FOREIGN KEY (session_id)
        REFERENCES sessions(session_id)
        ON DELETE CASCADE
);

-- ==========================================
-- INDEXES
-- ==========================================
CREATE INDEX idx_messages_session_time
    ON messages(session_id, sending_time DESC);

CREATE INDEX idx_messages_sending_time
    ON messages(sending_time DESC);

-- ==========================================
-- TRIGGERS
-- ==========================================

-- Update session last_active on message insert
CREATE OR REPLACE FUNCTION update_session_last_active()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE sessions
    SET last_active = NOW()
    WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_session_last_active
AFTER INSERT ON messages
FOR EACH ROW
EXECUTE FUNCTION update_session_last_active();