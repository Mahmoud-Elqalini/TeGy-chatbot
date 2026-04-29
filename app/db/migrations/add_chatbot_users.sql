-- ---------------------------------------------------------------------
-- Migration: Create chatbot_users projection table
-- Date: 2026-04-28
-- Purpose:
--   Lightweight replicated user table synced from Main Backend
--   Used for personalization inside Chatbot service
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS chatbot_users (
    user_id     UUID PRIMARY KEY,

    -- Basic profile data (denormalized from main system)
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    gender      VARCHAR(50)  NOT NULL,

    -- Audit timestamps
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Performance indexes
-- ---------------------------------------------------------------------

-- Primary key already creates index on user_id

-- Optional index for future lookup patterns (search by email)
CREATE INDEX IF NOT EXISTS idx_chatbot_users_email
    ON chatbot_users(email);

-- ---------------------------------------------------------------------
-- Auto-update trigger for updated_at
-- (Important for keeping projection consistent)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chatbot_users_updated_at ON chatbot_users;

CREATE TRIGGER trg_chatbot_users_updated_at
BEFORE UPDATE ON chatbot_users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();