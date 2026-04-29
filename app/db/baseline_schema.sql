-- ==========================================
-- 1. (DELETED) USERS - Handled by Main DB
-- ==========================================

-- ==========================================
-- 1b. CHATBOT USERS (Projection Layer)
-- Lightweight copy synced via upsert from Main Backend
-- ==========================================
CREATE TABLE IF NOT EXISTS chatbot_users (
    user_id    UUID        PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    email      VARCHAR(255) NOT NULL,
    gender     VARCHAR(50)  NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ==========================================
-- 2. MODEL SETTINGS 
-- ==========================================
CREATE TABLE model_settings (
    model_setting_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name       VARCHAR(100) NOT NULL,
    system_prompt    TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ==========================================
-- 3. SESSIONS
-- ==========================================
CREATE TABLE sessions (
    session_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL,
    model_setting_id UUID,                         
    title            VARCHAR(255),                 
    channel          VARCHAR(50)  DEFAULT 'web'
        CHECK (channel IN ('web', 'mobile', 'api', 'whatsapp', 'telegram')),
    status           VARCHAR(20)  DEFAULT 'active'
        CHECK (status IN ('active', 'closed', 'idle', 'archived')),
    current_intent   VARCHAR(255),
	current_summary  TEXT,
    last_active      TIMESTAMPTZ DEFAULT NOW(),
    created_at       TIMESTAMPTZ DEFAULT NOW(),

    -- FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE, (REMOVED: Decoupled Architecture)
    FOREIGN KEY (model_setting_id) REFERENCES model_settings(model_setting_id) ON DELETE SET NULL
);

-- ==========================================
-- 4. MESSAGES
-- ==========================================
CREATE TABLE messages (
    message_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL,
    role        VARCHAR(20) NOT NULL
        CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content     TEXT    NOT NULL,
    token_count INT     DEFAULT 0,
    is_deleted  BOOLEAN DEFAULT FALSE,
    metadata    JSONB,
    sending_time TIMESTAMPTZ DEFAULT NOW(),        

    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- ==========================================
-- 5. SESSION MEMORY
-- ==========================================
CREATE TABLE session_memory (
    memory_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL,
    memory_type VARCHAR(50),
    content     TEXT  NOT NULL,
    importance  FLOAT DEFAULT 0.5
        CHECK (importance BETWEEN 0.0 AND 1.0),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),

    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- ==========================================
-- 6. CONV SUMMARIES
-- ==========================================
CREATE TABLE conv_summaries (
    summarize_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL,
    summary      TEXT NOT NULL,
    version      INT  NOT NULL DEFAULT 1,
    time         TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_summary_version UNIQUE (session_id, version),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- ==========================================
-- INDEXES
-- ==========================================
-- CREATE INDEX idx_users_source          ON users(user_source_id); (REMOVED)
CREATE INDEX idx_sessions_user         ON sessions(user_id);
CREATE INDEX idx_sessions_last_active  ON sessions(last_active);
CREATE INDEX idx_messages_session_time ON messages(session_id, sending_time DESC);
CREATE INDEX idx_messages_sending_time ON messages(sending_time DESC);
CREATE INDEX idx_memory_session        ON session_memory(session_id);
CREATE INDEX idx_summaries_session     ON conv_summaries(session_id);

-- ==========================================
-- TRIGGERS
-- ==========================================

-- last_active
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
FOR EACH ROW EXECUTE FUNCTION update_session_last_active();

-- updated_at على session_memory
CREATE OR REPLACE FUNCTION update_memory_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_memory_updated_at
BEFORE UPDATE ON session_memory
FOR EACH ROW EXECUTE FUNCTION update_memory_updated_at();

-- ==========================================
-- EXTENSION
-- ==========================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";