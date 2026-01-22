-- =====================================================
-- SUPABASE SCHEMA FOR EVL TASK BOT
-- =====================================================

-- GUILDS table
-- Stores configuration and state for each Discord server
CREATE TABLE IF NOT EXISTS guilds (
    guild_id TEXT PRIMARY KEY,
    server_name TEXT,
    owner_id TEXT,
    member_count INTEGER DEFAULT 0,
    icon_url TEXT,
    prefix TEXT DEFAULT '!',
    currency_name TEXT DEFAULT 'coins',
    currency_symbol TEXT DEFAULT '$',
    
    -- Feature flags
    feature_currency BOOLEAN DEFAULT true,
    feature_tasks BOOLEAN DEFAULT true,
    feature_shop BOOLEAN DEFAULT true,
    feature_announcements BOOLEAN DEFAULT true,
    feature_moderation BOOLEAN DEFAULT true,

    -- Channel configurations
    log_channel_id TEXT,
    welcome_channel_id TEXT,
    task_channel_id TEXT,
    shop_channel_id TEXT,
    
    -- Roles
    admin_roles JSONB DEFAULT '[]'::jsonb,
    moderator_roles JSONB DEFAULT '[]'::jsonb,
    
    -- Global settings
    global_shop BOOLEAN DEFAULT false,
    global_tasks BOOLEAN DEFAULT false,
    
    -- Bot Status
    bot_status_message TEXT,
    bot_status_type TEXT DEFAULT 'playing',

    -- Subscription
    subscription_tier TEXT DEFAULT 'free', -- 'free' or 'premium'
    subscription_expiry TIMESTAMPTZ,

    -- Boost Rewards
    boost_reward_enabled BOOLEAN DEFAULT true,
    boost_reward_amount INTEGER DEFAULT 1000,
    boost_log_channel_id TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_synced TIMESTAMP WITH TIME ZONE
);

-- USERS table
-- Stores economy and profile data for users within guilds
CREATE TABLE IF NOT EXISTS users (
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT,
    username TEXT,
    display_name TEXT,
    
    balance NUMERIC DEFAULT 0,
    total_earned NUMERIC DEFAULT 0,
    total_spent NUMERIC DEFAULT 0,
    
    last_daily TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (guild_id, user_id)
);

-- SHOP ITEMS table
CREATE TABLE IF NOT EXISTS shop_items (
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    item_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    price NUMERIC NOT NULL CHECK (price >= 0),
    category TEXT DEFAULT 'general',
    stock INTEGER DEFAULT -1, -- -1 means infinite
    emoji TEXT DEFAULT '🛍️',
    is_active BOOLEAN DEFAULT true,
    
    message_id TEXT,
    channel_id TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (guild_id, item_id)
);

-- INVENTORY table
CREATE TABLE IF NOT EXISTS inventory (
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT,
    item_id TEXT, -- References shop_items(item_id) conceptually, but shop_items PK is composite
    quantity INTEGER DEFAULT 1 CHECK (quantity >= 0),
    
    acquired_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (guild_id, user_id, item_id)
);

-- TASKS table
CREATE TABLE IF NOT EXISTS tasks (
    task_id BIGINT,
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    
    name TEXT NOT NULL,
    description TEXT,
    reward NUMERIC NOT NULL CHECK (reward >= 0),
    duration_hours INTEGER DEFAULT 24,
    status TEXT DEFAULT 'active', -- active, archived, completed
    
    expires_at TIMESTAMP WITH TIME ZONE,
    
    channel_id TEXT,
    message_id TEXT,
    
    max_claims INTEGER DEFAULT -1,
    current_claims INTEGER DEFAULT 0,
    assigned_users JSONB DEFAULT '[]'::jsonb,
    
    category TEXT DEFAULT 'general',
    role_name TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (guild_id, task_id)
);

-- USER TASKS table (tracking claims)
CREATE TABLE IF NOT EXISTS user_tasks (
    guild_id TEXT,
    user_id TEXT,
    task_id BIGINT,
    
    status TEXT DEFAULT 'in_progress', -- in_progress, submitted, completed, cancelled
    
    claimed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deadline TIMESTAMP WITH TIME ZONE,
    
    proof_content TEXT,
    proof_message_id TEXT,
    proof_attachments JSONB DEFAULT '[]'::jsonb,
    
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    notes TEXT,
    
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (guild_id, user_id, task_id),
    FOREIGN KEY (guild_id, task_id) REFERENCES tasks(guild_id, task_id) ON DELETE CASCADE
);

-- TASK SETTINGS table
CREATE TABLE IF NOT EXISTS task_settings (
    guild_id TEXT PRIMARY KEY REFERENCES guilds(guild_id) ON DELETE CASCADE,
    
    allow_user_tasks BOOLEAN DEFAULT true,
    max_tasks_per_user INTEGER DEFAULT 10,
    auto_expire_enabled BOOLEAN DEFAULT true,
    require_proof BOOLEAN DEFAULT true,
    
    announcement_channel_id TEXT,
    next_task_id BIGINT DEFAULT 1,
    
    total_completed INTEGER DEFAULT 0,
    total_expired INTEGER DEFAULT 0,
    
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- TRANSACTIONS table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT,
    
    amount NUMERIC NOT NULL,
    balance_before NUMERIC,
    balance_after NUMERIC,
    
    transaction_type TEXT, -- command, shop, task, daily, admin
    description TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    "timestamp" TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ANNOUNCEMENTS table
CREATE TABLE IF NOT EXISTS announcements (
    announcement_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    
    title TEXT NOT NULL,
    content TEXT,
    embed_data JSONB,
    
    channel_id TEXT,
    message_id TEXT,
    
    is_pinned BOOLEAN DEFAULT false,
    status TEXT DEFAULT 'published',
    
    created_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- EMBEDS table
CREATE TABLE IF NOT EXISTS embeds (
    embed_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    
    title TEXT,
    description TEXT,
    color TEXT,
    fields JSONB DEFAULT '[]'::jsonb,
    footer TEXT,
    thumbnail TEXT,
    image TEXT,
    
    channel_id TEXT,
    message_id TEXT,
    
    created_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- SERVER BOOSTS table
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

-- GUILD ROLES table (for syncing)
CREATE TABLE IF NOT EXISTS guild_roles (
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    role_id TEXT,
    role_name TEXT,
    role_color TEXT,
    role_position INTEGER,
    is_managed BOOLEAN DEFAULT false,
    permissions BIGINT,
    last_synced TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (guild_id, role_id)
);

-- USER ROLES table (for syncing)
CREATE TABLE IF NOT EXISTS user_roles (
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT,
    role_id TEXT,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id, role_id)
);

-- =====================================================
-- CHANNEL LOCK SCHEDULES TABLE (Premium Feature)
-- =====================================================

-- Table to store scheduled channel lock/unlock configurations
CREATE TABLE IF NOT EXISTS channel_schedules (
    schedule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    
    -- Schedule configuration
    is_enabled BOOLEAN DEFAULT true,
    unlock_time TIME NOT NULL,           -- Time to unlock (e.g., '09:00:00')
    lock_time TIME NOT NULL,             -- Time to lock (e.g., '21:00:00')
    timezone TEXT DEFAULT 'America/New_York',  -- User's timezone (IANA format)
    
    -- Days of week the schedule is active (0=Sunday, 6=Saturday)
    active_days INTEGER[] DEFAULT ARRAY[0, 1, 2, 3, 4, 5, 6],
    
    -- Current state tracking
    current_state TEXT DEFAULT 'locked' CHECK (current_state IN ('locked', 'unlocked', 'error')),
    last_state_change TIMESTAMPTZ,
    last_error TEXT,
    
    -- Permission snapshot (to restore original permissions if needed)
    original_permissions JSONB,
    
    -- Metadata
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Prevent duplicate schedules for the same channel in a guild
    UNIQUE(guild_id, channel_id)
);

-- Index for efficient schedule lookups
CREATE INDEX IF NOT EXISTS idx_channel_schedules_guild ON channel_schedules(guild_id);
CREATE INDEX IF NOT EXISTS idx_channel_schedules_enabled ON channel_schedules(is_enabled) WHERE is_enabled = true;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_channel_schedules_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update timestamp
DROP TRIGGER IF EXISTS channel_schedules_timestamp ON channel_schedules;
CREATE TRIGGER channel_schedules_timestamp
    BEFORE UPDATE ON channel_schedules
    FOR EACH ROW
    EXECUTE FUNCTION update_channel_schedules_timestamp();

-- Enable RLS
ALTER TABLE channel_schedules ENABLE ROW LEVEL SECURITY;

-- Policy for anon access (matches existing pattern in the codebase)
DROP POLICY IF EXISTS "Allow public access to channel_schedules" ON channel_schedules;
CREATE POLICY "Allow public access to channel_schedules" 
    ON channel_schedules 
    FOR ALL 
    TO anon 
    USING (true) 
    WITH CHECK (true);

-- Add comment for documentation
COMMENT ON TABLE channel_schedules IS 'Stores scheduled channel lock/unlock configurations for premium guilds';
COMMENT ON COLUMN channel_schedules.unlock_time IS 'Time of day when the channel should be unlocked (in the specified timezone)';
COMMENT ON COLUMN channel_schedules.lock_time IS 'Time of day when the channel should be locked (in the specified timezone)';
COMMENT ON COLUMN channel_schedules.timezone IS 'IANA timezone identifier (e.g., America/New_York, Europe/London)';
COMMENT ON COLUMN channel_schedules.active_days IS 'Array of weekdays when schedule is active (0=Sunday through 6=Saturday)';
