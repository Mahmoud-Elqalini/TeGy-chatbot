-- Run order: core.sql → sessions.sql → messages.sql → session_memory.sql → conv_summaries.sql

-- ==========================================
-- EXTENSION
-- ==========================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==========================================
-- 1. CHATBOT USERS (Projection Layer)
-- ==========================================
CREATE TABLE IF NOT EXISTS chatbot_users (
    user_id    UUID PRIMARY KEY,
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