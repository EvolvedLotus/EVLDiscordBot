-- AD VIEWS table
-- Tracks individual ad viewing sessions (Monetag/Custom)
CREATE TABLE IF NOT EXISTS ad_views (
    ad_session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    
    ad_type TEXT DEFAULT 'monetag_interstitial',
    
    is_verified BOOLEAN DEFAULT false,
    verified_at TIMESTAMP WITH TIME ZONE,
    
    reward_amount INTEGER DEFAULT 10,
    reward_granted BOOLEAN DEFAULT false,
    transaction_id UUID,
    
    ip_address TEXT,
    user_agent TEXT,
    
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for ad_views
CREATE INDEX IF NOT EXISTS idx_ad_views_user ON ad_views(user_id);
CREATE INDEX IF NOT EXISTS idx_ad_views_created_at ON ad_views(created_at);
CREATE INDEX IF NOT EXISTS idx_ad_views_session ON ad_views(ad_session_id);

-- GLOBAL TASK CLAIMS table
-- Tracks completion of global tasks like ad watching
CREATE TABLE IF NOT EXISTS global_task_claims (
    claim_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    task_key TEXT NOT NULL,
    
    ad_session_id TEXT REFERENCES ad_views(ad_session_id),
    
    reward_amount NUMERIC DEFAULT 10,
    reward_granted BOOLEAN DEFAULT false,
    
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_global_task_claims_user ON global_task_claims(user_id);
