-- WEB SESSIONS table
-- Replaces in-memory session storage
CREATE TABLE IF NOT EXISTS web_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT, -- Can be null for unauthenticated sessions if needed, but usually linked to admin_user
    user_data JSONB, -- Cache of critical user data to avoid extra lookups
    
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    ip_address TEXT,
    user_agent TEXT,
    
    is_valid BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_web_sessions_expires ON web_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_web_sessions_user ON web_sessions(user_id);

-- AD LIMITS table (Optional optimization, but good for enforcement)
CREATE TABLE IF NOT EXISTS user_daily_limits (
    user_id TEXT,
    guild_id TEXT,
    date DATE DEFAULT CURRENT_DATE,
    
    ad_claims INTEGER DEFAULT 0,
    last_claim_at TIMESTAMP WITH TIME ZONE,
    
    PRIMARY KEY (user_id, guild_id, date)
);
