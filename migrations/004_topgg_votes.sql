-- TOP.GG VOTE LOGS TABLE
-- Tracks all votes from Top.gg for analytics and preventing duplicate rewards

CREATE TABLE IF NOT EXISTS vote_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    vote_type TEXT NOT NULL, -- 'bot' or 'server'
    target_id TEXT NOT NULL, -- bot ID or server ID that was voted for
    reward INTEGER NOT NULL DEFAULT 100,
    is_weekend BOOLEAN DEFAULT false,
    platform TEXT DEFAULT 'topgg', -- for future expansion (other vote sites)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for querying by user
CREATE INDEX IF NOT EXISTS idx_vote_logs_user_id ON vote_logs(user_id);

-- Index for querying by date (for analytics)
CREATE INDEX IF NOT EXISTS idx_vote_logs_created_at ON vote_logs(created_at);

-- Optional: Prevent duplicate votes within 12 hours
-- (Top.gg already handles this, but this is extra safety)
CREATE INDEX IF NOT EXISTS idx_vote_logs_user_recent ON vote_logs(user_id, created_at DESC);
