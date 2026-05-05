-- Run order: core.sql → sessions.sql → messages.sql → session_memory.sql → conv_summaries.sql

-- ==========================================
-- 3. SESSIONS
-- ==========================================
CREATE TABLE sessions (
    session_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL,
    model_setting_id UUID,
    title            VARCHAR(255),
    channel          VARCHAR(50) DEFAULT 'web'
        CHECK (channel IN ('web', 'mobile', 'api', 'whatsapp', 'telegram')),
    status           VARCHAR(20) DEFAULT 'active'
        CHECK (status IN ('active', 'closed', 'idle', 'archived')),
    current_intent   VARCHAR(255),
    current_summary  TEXT,
    system_prompt    TEXT,
    last_active      TIMESTAMPTZ DEFAULT NOW(),
    created_at       TIMESTAMPTZ DEFAULT NOW(),

    FOREIGN KEY (model_setting_id)
        REFERENCES model_settings(model_setting_id)
        ON DELETE SET NULL
);

-- ==========================================
-- INDEXES
-- ==========================================
CREATE INDEX idx_sessions_user
    ON sessions(user_id);

CREATE INDEX idx_sessions_last_active
    ON sessions(last_active);