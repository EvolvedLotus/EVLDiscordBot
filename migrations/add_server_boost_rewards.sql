-- =====================================================
-- SERVER BOOST REWARDS SYSTEM MIGRATION
-- Run this on your Supabase database to enable boost rewards
-- =====================================================

-- Add boost configuration columns to guilds table
ALTER TABLE guilds
ADD COLUMN IF NOT EXISTS boost_reward_enabled BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS boost_reward_amount INTEGER DEFAULT 1000 CHECK (boost_reward_amount >= 0),
ADD COLUMN IF NOT EXISTS boost_log_channel_id TEXT;

-- Server boosts tracking table
CREATE TABLE IF NOT EXISTS server_boosts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    boost_type TEXT DEFAULT 'new' CHECK (boost_type IN ('new', 'renewed')),
    boosted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_reward_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    unboosted_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(guild_id, user_id)
);

-- Indexes for server boosts
CREATE INDEX IF NOT EXISTS idx_server_boosts_guild ON server_boosts(guild_id);
CREATE INDEX IF NOT EXISTS idx_server_boosts_user ON server_boosts(user_id);
CREATE INDEX IF NOT EXISTS idx_server_boosts_active ON server_boosts(is_active);
CREATE INDEX IF NOT EXISTS idx_server_boosts_last_reward ON server_boosts(last_reward_at);

-- Trigger for server boosts updated_at
DROP TRIGGER IF EXISTS update_server_boosts_updated_at ON server_boosts;
CREATE TRIGGER update_server_boosts_updated_at
BEFORE UPDATE ON server_boosts
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Row level security for server boosts
ALTER TABLE server_boosts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access" ON server_boosts;
CREATE POLICY "Service role full access" ON server_boosts FOR ALL USING (true);

-- Comments
COMMENT ON TABLE server_boosts IS 'Tracks server boost history and rewards for users';
COMMENT ON COLUMN guilds.boost_reward_enabled IS 'Whether boost rewards are enabled for this guild';
COMMENT ON COLUMN guilds.boost_reward_amount IS 'Amount of coins to reward per boost';
COMMENT ON COLUMN guilds.boost_log_channel_id IS 'Channel to log boost events';

-- =====================================================
-- VERIFICATION
-- =====================================================
-- Run these queries to verify the migration was successful:
-- 
-- 1. Check if columns were added to guilds table:
--    SELECT column_name, data_type, column_default 
--    FROM information_schema.columns 
--    WHERE table_name = 'guilds' AND column_name LIKE 'boost%';
--
-- 2. Check if server_boosts table was created:
--    SELECT * FROM server_boosts LIMIT 1;
--
-- 3. Check indexes:
--    SELECT indexname FROM pg_indexes WHERE tablename = 'server_boosts';
--
-- =====================================================
