-- Migration 009: Moderation system enhancements
-- Creates missing strikes and moderation actions tables
-- Supports warning TTLs safely

CREATE TABLE IF NOT EXISTS strikes (
    id SERIAL PRIMARY KEY,
    strike_id TEXT UNIQUE NOT NULL,
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    reason TEXT,
    moderator_id TEXT NOT NULL,
    auto_generated BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_strikes_user_active_expiry ON strikes(user_id, guild_id, is_active, expires_at);

CREATE TABLE IF NOT EXISTS moderation_actions (
    id SERIAL PRIMARY KEY,
    action_id TEXT UNIQUE NOT NULL,
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    action_type TEXT NOT NULL, -- warn, mute, kick, ban, clear
    reason TEXT,
    moderator_id TEXT NOT NULL,
    duration_seconds INTEGER,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mod_actions_guild ON moderation_actions(guild_id, user_id, action_type);
