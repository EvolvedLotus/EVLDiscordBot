-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =====================================================
-- GUILDS TABLE (Server Configurations)
-- =====================================================
CREATE TABLE IF NOT EXISTS guilds (
guild_id TEXT PRIMARY KEY,
server_name TEXT NOT NULL,
owner_id TEXT NOT NULL,
member_count INTEGER DEFAULT 0,
icon_url TEXT,
-- Configuration
prefix TEXT DEFAULT '!',
currency_name TEXT DEFAULT 'coins',
currency_symbol TEXT DEFAULT '$',
admin_roles TEXT[] DEFAULT '{}',
moderator_roles TEXT[] DEFAULT '{}',

-- Channel IDs (standardized with _id suffix)
log_channel_id TEXT,
welcome_channel_id TEXT,
task_channel_id TEXT,
shop_channel_id TEXT,

-- Feature toggles
feature_currency BOOLEAN DEFAULT true,
feature_tasks BOOLEAN DEFAULT true,
feature_shop BOOLEAN DEFAULT true,
feature_announcements BOOLEAN DEFAULT true,
feature_moderation BOOLEAN DEFAULT true,

-- Settings
global_shop BOOLEAN DEFAULT false,
global_tasks BOOLEAN DEFAULT false,
bot_status_message TEXT,  -- Custom bot status message
bot_status_type TEXT DEFAULT 'watching',  -- Activity type: playing, streaming, listening, watching

-- Metadata
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
last_sync TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
is_active BOOLEAN DEFAULT true,
left_at TIMESTAMP WITH TIME ZONE
);

-- =====================================================
-- USERS TABLE (User Balances & Activity)
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
user_id TEXT NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
-- Currency
balance INTEGER DEFAULT 0 CHECK (balance >= 0),
total_earned INTEGER DEFAULT 0,
total_spent INTEGER DEFAULT 0,

-- Activity
last_daily TIMESTAMP WITH TIME ZONE,
is_active BOOLEAN DEFAULT true,

-- Metadata
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

UNIQUE(user_id, guild_id)
);

-- =====================================================
-- TRANSACTIONS TABLE (Currency Movement Log)
-- =====================================================
CREATE TABLE IF NOT EXISTS transactions (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
transaction_id TEXT UNIQUE NOT NULL,
user_id TEXT NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
-- Transaction details
amount INTEGER NOT NULL,
balance_before INTEGER NOT NULL,
balance_after INTEGER NOT NULL,
transaction_type TEXT NOT NULL,
description TEXT,

-- Metadata
metadata JSONB DEFAULT '{}',
"timestamp" TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

-- Validation
CHECK (balance_after = balance_before + amount)
);

-- =====================================================
-- SHOP_ITEMS TABLE (Products & Stock)
-- =====================================================
CREATE TABLE IF NOT EXISTS shop_items (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
item_id TEXT NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
-- Item details
name TEXT NOT NULL,
description TEXT,
price INTEGER NOT NULL CHECK (price > 0),
category TEXT DEFAULT 'misc',
stock INTEGER DEFAULT -1,
emoji TEXT,

-- Role-specific fields (for category='role')
role_id TEXT,  -- Discord role ID to assign
duration_minutes INTEGER DEFAULT 60,  -- Duration in minutes (for role items)

-- Discord integration
channel_id TEXT,
message_id TEXT,

-- Status
is_active BOOLEAN DEFAULT true,

-- Metadata
metadata JSONB DEFAULT '{}',
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

UNIQUE(guild_id, item_id)
);

-- =====================================================
-- INVENTORY TABLE (User Item Ownership)
-- =====================================================
CREATE TABLE IF NOT EXISTS inventory (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
user_id TEXT NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
item_id TEXT NOT NULL,
quantity INTEGER DEFAULT 0 CHECK (quantity >= 0),
-- Metadata
acquired_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

UNIQUE(user_id, guild_id, item_id)
);

-- =====================================================
-- TASKS TABLE (Task Definitions)
-- =====================================================
CREATE TABLE IF NOT EXISTS tasks (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
task_id INTEGER NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
-- Task details
name TEXT NOT NULL,
description TEXT,
reward INTEGER NOT NULL CHECK (reward > 0),
duration_hours INTEGER NOT NULL CHECK (duration_hours > 0),

-- Assignment
category TEXT DEFAULT 'General',
role_name TEXT,
assigned_users TEXT[] DEFAULT '{}',

-- Limits
max_claims INTEGER DEFAULT -1,
current_claims INTEGER DEFAULT 0,

-- Status
status TEXT DEFAULT 'active' CHECK (status IN ('active', 'completed', 'expired', 'cancelled')),

-- Discord integration
channel_id TEXT,
message_id TEXT,

-- Timestamps
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
expires_at TIMESTAMP WITH TIME ZONE,

UNIQUE(guild_id, task_id)
);

-- =====================================================
-- USER_TASKS TABLE (Task Progress)
-- =====================================================
CREATE TABLE IF NOT EXISTS user_tasks (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
user_id TEXT NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
task_id INTEGER NOT NULL,
-- Progress
status TEXT DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'submitted', 'accepted', 'rejected', 'expired')),

-- Proof
proof_message_id TEXT,
proof_attachments TEXT[] DEFAULT '{}',
proof_content TEXT,
notes TEXT,

-- Timestamps
claimed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
deadline TIMESTAMP WITH TIME ZONE NOT NULL,
submitted_at TIMESTAMP WITH TIME ZONE,
completed_at TIMESTAMP WITH TIME ZONE,

UNIQUE(user_id, guild_id, task_id)
);

-- =====================================================
-- TASK_SETTINGS TABLE (Task Configuration)
-- =====================================================
CREATE TABLE IF NOT EXISTS task_settings (
guild_id TEXT PRIMARY KEY REFERENCES guilds(guild_id) ON DELETE CASCADE,
allow_user_tasks BOOLEAN DEFAULT true,
max_tasks_per_user INTEGER DEFAULT 10,
auto_expire_enabled BOOLEAN DEFAULT true,
require_proof BOOLEAN DEFAULT true,
announcement_channel_id TEXT,

-- Metadata
next_task_id INTEGER DEFAULT 1,
total_completed INTEGER DEFAULT 0,
total_expired INTEGER DEFAULT 0,

created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- ANNOUNCEMENTS TABLE (Server Announcements)
-- =====================================================
CREATE TABLE IF NOT EXISTS announcements (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
announcement_id TEXT NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
-- Content
title TEXT,
content TEXT NOT NULL,
embed_data JSONB,

-- Discord integration
channel_id TEXT NOT NULL,
message_id TEXT,
is_pinned BOOLEAN DEFAULT false,

-- Metadata
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
created_by TEXT,

UNIQUE(guild_id, announcement_id)
);

-- =====================================================
-- EMBEDS TABLE (Custom Discord Embeds)
-- =====================================================
CREATE TABLE IF NOT EXISTS embeds (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
embed_id TEXT NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
-- Embed content
title TEXT,
description TEXT,
color TEXT,
fields JSONB DEFAULT '[]',
footer JSONB,
thumbnail JSONB,
image JSONB,

-- Discord integration
channel_id TEXT,
message_id TEXT,

-- Metadata
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
created_by TEXT,

UNIQUE(guild_id, embed_id)
);

-- =====================================================
-- ADMIN_USERS TABLE (Dashboard Authentication)
-- =====================================================
CREATE TABLE IF NOT EXISTS admin_users (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
username TEXT UNIQUE NOT NULL,
password_hash TEXT NOT NULL,
-- Permissions
is_active BOOLEAN DEFAULT true,
is_superadmin BOOLEAN DEFAULT false,

-- Session
last_login TIMESTAMP WITH TIME ZONE,
refresh_token_hash TEXT,

-- Metadata
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- CACHE TABLE (Performance Optimization)
-- =====================================================
CREATE TABLE IF NOT EXISTS cache (
key TEXT PRIMARY KEY,
value JSONB NOT NULL,
expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- STRIKES TABLE (User Violations & Warnings)
-- =====================================================
CREATE TABLE IF NOT EXISTS strikes (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
strike_id TEXT NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
user_id TEXT NOT NULL,
reason TEXT NOT NULL,
moderator_id TEXT NOT NULL,
auto_generated BOOLEAN DEFAULT false,
expires_at TIMESTAMP WITH TIME ZONE,
is_active BOOLEAN DEFAULT true,

-- Metadata
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

UNIQUE(guild_id, strike_id)
);

-- =====================================================
-- MODERATION_AUDIT_LOGS TABLE (Action Logging)
-- =====================================================
CREATE TABLE IF NOT EXISTS moderation_audit_logs (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
audit_id TEXT UNIQUE NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
action TEXT NOT NULL,
user_id TEXT NOT NULL,
moderator_id TEXT NOT NULL,
message_id TEXT,
details JSONB DEFAULT '{}',
can_undo BOOLEAN DEFAULT false,

-- Metadata
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- SCHEDULED_JOBS TABLE (Automated Moderation Tasks)
-- =====================================================
CREATE TABLE IF NOT EXISTS scheduled_jobs (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
job_id TEXT UNIQUE NOT NULL,
guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
user_id TEXT,
job_type TEXT NOT NULL, -- 'unmute', 'unban', 'cleanup', etc.
execute_at TIMESTAMP WITH TIME ZONE NOT NULL,
is_executed BOOLEAN DEFAULT false,
executed_at TIMESTAMP WITH TIME ZONE,
job_data JSONB DEFAULT '{}',

-- Metadata
created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- INDEXES FOR PERFORMANCE
-- =====================================================
-- Guilds indexes
CREATE INDEX IF NOT EXISTS idx_guilds_active ON guilds(is_active);
CREATE INDEX IF NOT EXISTS idx_guilds_created ON guilds(created_at);

-- Users indexes
CREATE INDEX IF NOT EXISTS idx_users_guild ON users(guild_id);
CREATE INDEX IF NOT EXISTS idx_users_user_guild ON users(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance DESC);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);

-- Transactions indexes
CREATE INDEX IF NOT EXISTS idx_transactions_guild ON transactions(guild_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions("timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_guild_user ON transactions(guild_id, user_id);

-- Shop items indexes
CREATE INDEX IF NOT EXISTS idx_shop_items_guild ON shop_items(guild_id);
CREATE INDEX IF NOT EXISTS idx_shop_items_active ON shop_items(is_active);
CREATE INDEX IF NOT EXISTS idx_shop_items_category ON shop_items(category);

-- Inventory indexes
CREATE INDEX IF NOT EXISTS idx_inventory_user_guild ON inventory(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory(item_id);

-- Tasks indexes
CREATE INDEX IF NOT EXISTS idx_tasks_guild ON tasks(guild_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_expires ON tasks(expires_at);
CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);

-- User tasks indexes
CREATE INDEX IF NOT EXISTS idx_user_tasks_user ON user_tasks(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_user_tasks_task ON user_tasks(task_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_user_tasks_status ON user_tasks(status);
CREATE INDEX IF NOT EXISTS idx_user_tasks_deadline ON user_tasks(deadline);

-- Announcements indexes
CREATE INDEX IF NOT EXISTS idx_announcements_guild ON announcements(guild_id);
CREATE INDEX IF NOT EXISTS idx_announcements_message ON announcements(message_id);
CREATE INDEX IF NOT EXISTS idx_announcements_pinned ON announcements(is_pinned);

-- Embeds indexes
CREATE INDEX IF NOT EXISTS idx_embeds_guild ON embeds(guild_id);
CREATE INDEX IF NOT EXISTS idx_embeds_message ON embeds(message_id);

-- Admin users indexes
CREATE INDEX IF NOT EXISTS idx_admin_users_username ON admin_users(username);
CREATE INDEX IF NOT EXISTS idx_admin_users_active ON admin_users(is_active);

-- Cache indexes
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);

-- Strikes indexes
CREATE INDEX IF NOT EXISTS idx_strikes_guild ON strikes(guild_id);
CREATE INDEX IF NOT EXISTS idx_strikes_user ON strikes(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_strikes_active ON strikes(is_active);
CREATE INDEX IF NOT EXISTS idx_strikes_expires ON strikes(expires_at);

-- Moderation audit logs indexes
CREATE INDEX IF NOT EXISTS idx_moderation_audit_logs_guild ON moderation_audit_logs(guild_id);
CREATE INDEX IF NOT EXISTS idx_moderation_audit_logs_user ON moderation_audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_moderation_audit_logs_action ON moderation_audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_moderation_audit_logs_created ON moderation_audit_logs(created_at DESC);

-- Scheduled jobs indexes
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_guild ON scheduled_jobs(guild_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_execute_at ON scheduled_jobs(execute_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_executed ON scheduled_jobs(is_executed);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_type ON scheduled_jobs(job_type);

-- =====================================================
-- TRIGGER FUNCTIONS
-- =====================================================
-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
NEW.updated_at = NOW();
RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers to all tables
DROP TRIGGER IF EXISTS update_guilds_updated_at ON guilds;
CREATE TRIGGER update_guilds_updated_at
BEFORE UPDATE ON guilds
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_shop_items_updated_at ON shop_items;
CREATE TRIGGER update_shop_items_updated_at
BEFORE UPDATE ON shop_items
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_inventory_updated_at ON inventory;
CREATE TRIGGER update_inventory_updated_at
BEFORE UPDATE ON inventory
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tasks_updated_at ON tasks;
CREATE TRIGGER update_tasks_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_tasks_updated_at ON user_tasks;
CREATE TRIGGER update_user_tasks_updated_at
BEFORE UPDATE ON user_tasks
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_task_settings_updated_at ON task_settings;
CREATE TRIGGER update_task_settings_updated_at
BEFORE UPDATE ON task_settings
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_announcements_updated_at ON announcements;
CREATE TRIGGER update_announcements_updated_at
BEFORE UPDATE ON announcements
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_embeds_updated_at ON embeds;
CREATE TRIGGER update_embeds_updated_at
BEFORE UPDATE ON embeds
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_admin_users_updated_at ON admin_users;
CREATE TRIGGER update_admin_users_updated_at
BEFORE UPDATE ON admin_users
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_strikes_updated_at ON strikes;
CREATE TRIGGER update_strikes_updated_at
BEFORE UPDATE ON strikes
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_scheduled_jobs_updated_at ON scheduled_jobs;
CREATE TRIGGER update_scheduled_jobs_updated_at
BEFORE UPDATE ON scheduled_jobs
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- DATABASE FUNCTIONS (Stored Procedures)
-- =====================================================
-- Get user balance safely
CREATE OR REPLACE FUNCTION get_user_balance(p_user_id TEXT, p_guild_id TEXT)
RETURNS INTEGER AS $$
DECLARE
v_balance INTEGER;
BEGIN
SELECT balance INTO v_balance
FROM users
WHERE user_id = p_user_id AND guild_id = p_guild_id;
RETURN COALESCE(v_balance, 0);
END;
$$ LANGUAGE plpgsql;

-- Update user balance atomically
CREATE OR REPLACE FUNCTION update_user_balance(
p_user_id TEXT,
p_guild_id TEXT,
p_amount INTEGER,
p_description TEXT,
p_transaction_type TEXT,
p_metadata JSONB DEFAULT '{}'
) RETURNS TABLE(
new_balance INTEGER,
transaction_id TEXT
) AS $$
DECLARE
v_balance_before INTEGER;
v_balance_after INTEGER;
v_transaction_id TEXT;
BEGIN
-- Get or create user
INSERT INTO users (user_id, guild_id, balance)
VALUES (p_user_id, p_guild_id, 0)
ON CONFLICT (user_id, guild_id) DO NOTHING;

-- Lock row and get current balance
SELECT balance INTO v_balance_before
FROM users
WHERE user_id = p_user_id AND guild_id = p_guild_id
FOR UPDATE;

-- Calculate new balance
v_balance_after := v_balance_before + p_amount;

-- Prevent negative balance
IF v_balance_after < 0 THEN
    RAISE EXCEPTION 'Insufficient balance';
END IF;

-- Update balance
UPDATE users
SET balance = v_balance_after,
    total_earned = total_earned + GREATEST(p_amount, 0),
    total_spent = total_spent + GREATEST(-p_amount, 0),
    updated_at = NOW()
WHERE user_id = p_user_id AND guild_id = p_guild_id;

-- Generate transaction ID
v_transaction_id := 'txn_' || p_user_id || '_' || EXTRACT(EPOCH FROM NOW())::BIGINT || '_' || substring(md5(random()::text) from 1 for 8);

-- Log transaction
INSERT INTO transactions (
    transaction_id,
    user_id,
    guild_id,
    amount,
    balance_before,
    balance_after,
    transaction_type,
    description,
    metadata
) VALUES (
    v_transaction_id,
    p_user_id,
    p_guild_id,
    p_amount,
    v_balance_before,
    v_balance_after,
    p_transaction_type,
    p_description,
    p_metadata
);

RETURN QUERY SELECT v_balance_after, v_transaction_id;
END;
$$ LANGUAGE plpgsql;

-- Atomic transaction logging function (used by TransactionManager)
-- Updated to match TransactionManager expectations and include balance updates

-- Cleanup expired cache entries
CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS INTEGER AS $$
DECLARE
v_deleted_count INTEGER;
BEGIN
DELETE FROM cache WHERE expires_at < NOW();
GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Cleanup expired strikes
CREATE OR REPLACE FUNCTION cleanup_expired_strikes()
RETURNS INTEGER AS $$
DECLARE
v_deleted_count INTEGER;
BEGIN
UPDATE strikes SET is_active = false WHERE expires_at < NOW() AND is_active = true;
GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Execute scheduled jobs
CREATE OR REPLACE FUNCTION execute_scheduled_jobs()
RETURNS INTEGER AS $$
DECLARE
v_executed_count INTEGER := 0;
v_job_record RECORD;
BEGIN
FOR v_job_record IN
    SELECT job_id, job_type, job_data, guild_id, user_id
    FROM scheduled_jobs
    WHERE execute_at <= NOW() AND is_executed = false
    ORDER BY execute_at ASC
LOOP
    -- Mark job as executed
    UPDATE scheduled_jobs
    SET is_executed = true, executed_at = NOW()
    WHERE job_id = v_job_record.job_id;

    -- Here you would add logic to actually execute the job based on job_type
    -- For now, just count the executions
    v_executed_count := v_executed_count + 1;

    -- Log the execution
    INSERT INTO moderation_audit_logs (
        audit_id,
        guild_id,
        action,
        user_id,
        moderator_id,
        details
    ) VALUES (
        'job_' || v_job_record.job_id || '_' || EXTRACT(EPOCH FROM NOW())::BIGINT,
        v_job_record.guild_id,
        'scheduled_job_executed',
        COALESCE(v_job_record.user_id, 'system'),
        'system',
        jsonb_build_object(
            'job_type', v_job_record.job_type,
            'job_data', v_job_record.job_data
        )
    );
END LOOP;

RETURN v_executed_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- ROW LEVEL SECURITY (RLS)
-- =====================================================
-- Enable RLS on all tables
ALTER TABLE guilds ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE shop_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE announcements ENABLE ROW LEVEL SECURITY;
ALTER TABLE embeds ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE strikes ENABLE ROW LEVEL SECURITY;
ALTER TABLE moderation_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_jobs ENABLE ROW LEVEL SECURITY;

-- Service role bypass (for backend operations)
-- Create policies that allow service role full access
DROP POLICY IF EXISTS "Service role full access" ON guilds;
CREATE POLICY "Service role full access" ON guilds FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON users;
CREATE POLICY "Service role full access" ON users FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON transactions;
CREATE POLICY "Service role full access" ON transactions FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON shop_items;
CREATE POLICY "Service role full access" ON shop_items FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON inventory;
CREATE POLICY "Service role full access" ON inventory FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON tasks;
CREATE POLICY "Service role full access" ON tasks FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON user_tasks;
CREATE POLICY "Service role full access" ON user_tasks FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON task_settings;
CREATE POLICY "Service role full access" ON task_settings FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON announcements;
CREATE POLICY "Service role full access" ON announcements FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON embeds;
CREATE POLICY "Service role full access" ON embeds FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON admin_users;
CREATE POLICY "Service role full access" ON admin_users FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON cache;
CREATE POLICY "Service role full access" ON cache FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON strikes;
CREATE POLICY "Service role full access" ON strikes FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON moderation_audit_logs;
CREATE POLICY "Service role full access" ON moderation_audit_logs FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON scheduled_jobs;
CREATE POLICY "Service role full access" ON scheduled_jobs FOR ALL USING (true);

-- =====================================================
-- INACTIVITY SYSTEM MIGRATIONS
-- =====================================================

-- Add inactivity_days column to guilds table
ALTER TABLE guilds
ADD COLUMN IF NOT EXISTS inactivity_days INTEGER DEFAULT 30 CHECK (inactivity_days > 0);

-- =====================================================
-- INACTIVITY SYSTEM FUNCTIONS
-- =====================================================

-- Stored procedure to atomically mark users as inactive
CREATE OR REPLACE FUNCTION mark_inactive_users(
    p_guild_id TEXT,
    p_cutoff_date TIMESTAMP WITH TIME ZONE
)
RETURNS INTEGER AS $$
DECLARE
    affected_count INTEGER;
BEGIN
    -- Mark users as inactive if their last update was before cutoff
    -- and they have no recent transactions
    UPDATE users
    SET is_active = false,
        updated_at = NOW()
    WHERE guild_id = p_guild_id
        AND is_active = true
        AND updated_at < p_cutoff_date
        AND NOT EXISTS (
            SELECT 1 FROM transactions
            WHERE transactions.user_id = users.user_id
                AND transactions.guild_id = users.guild_id
                AND transactions."timestamp" > p_cutoff_date
        );

    GET DIAGNOSTICS affected_count = ROW_COUNT;
    RETURN affected_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- COMMAND PERMISSIONS TABLE (CMS Permission Management)
-- =====================================================
CREATE TABLE IF NOT EXISTS command_permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    command_name TEXT NOT NULL,
    allowed_roles TEXT[] DEFAULT '{}',
    denied_roles TEXT[] DEFAULT '{}',
    allowed_users TEXT[] DEFAULT '{}',
    denied_users TEXT[] DEFAULT '{}',
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(guild_id, command_name)
);

-- =====================================================
-- GUILD ROLES TABLE (Discord Role Mirror)
-- =====================================================
CREATE TABLE IF NOT EXISTS guild_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    role_id TEXT NOT NULL,
    role_name TEXT NOT NULL,
    role_color TEXT,
    role_position INTEGER DEFAULT 0,
    is_managed BOOLEAN DEFAULT false,
    permissions BIGINT DEFAULT 0,
    last_synced TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(guild_id, role_id)
);

-- =====================================================
-- USER ROLES TABLE (Role Assignments)
-- =====================================================
CREATE TABLE IF NOT EXISTS user_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_by TEXT,
    UNIQUE(guild_id, user_id, role_id)
);

-- =====================================================
-- MODERATION ACTIONS TABLE (Kick/Ban/Timeout Logging)
-- =====================================================
CREATE TABLE IF NOT EXISTS moderation_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action_id TEXT UNIQUE NOT NULL,
    guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('kick', 'ban', 'timeout', 'untimeout', 'unban')),
    reason TEXT,
    duration_seconds INTEGER,
    moderator_id TEXT NOT NULL,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true
);

-- =====================================================
-- MIGRATION: Standardize Channel Field Names
-- =====================================================
-- This handles existing databases by renaming old columns to new standard
-- Uses DO block for compatibility with all PostgreSQL versions

DO $$
BEGIN
    -- Rename welcome_channel to welcome_channel_id if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'guilds' AND column_name = 'welcome_channel'
    ) THEN
        ALTER TABLE guilds RENAME COLUMN welcome_channel TO welcome_channel_id;
    END IF;
    
    -- Rename log_channel to log_channel_id if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'guilds' AND column_name = 'log_channel'
    ) THEN
        ALTER TABLE guilds RENAME COLUMN log_channel TO log_channel_id;
    END IF;
    
    -- Drop logs_channel if it exists (duplicate)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'guilds' AND column_name = 'logs_channel'
    ) THEN
        ALTER TABLE guilds DROP COLUMN logs_channel;
    END IF;
    
    -- Drop last_channel_sync if it exists (unused)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'guilds' AND column_name = 'last_channel_sync'
    ) THEN
        ALTER TABLE guilds DROP COLUMN last_channel_sync;
    END IF;
END $$;

-- =====================================================
-- UPDATE GUILDS TABLE (Channel Field Comments)
-- =====================================================
-- Update comments to reflect standardized naming
COMMENT ON COLUMN guilds.task_channel_id IS 'Channel for task postings';
COMMENT ON COLUMN guilds.shop_channel_id IS 'Channel for shop item listings';
COMMENT ON COLUMN guilds.welcome_channel_id IS 'Channel for welcome messages';
COMMENT ON COLUMN guilds.log_channel_id IS 'Channel for moderation/action logs';

-- =====================================================
-- INDEXES FOR NEW TABLES
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_command_permissions_guild ON command_permissions(guild_id);
CREATE INDEX IF NOT EXISTS idx_guild_roles_guild ON guild_roles(guild_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_guild_user ON user_roles(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_moderation_actions_guild ON moderation_actions(guild_id);

-- =====================================================
-- TRIGGERS FOR NEW TABLES
-- =====================================================
DROP TRIGGER IF EXISTS update_command_permissions_updated_at ON command_permissions;
CREATE TRIGGER update_command_permissions_updated_at
BEFORE UPDATE ON command_permissions
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- RLS FOR NEW TABLES
-- =====================================================
ALTER TABLE command_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE guild_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE moderation_actions ENABLE ROW LEVEL SECURITY;

-- Service role bypass policies
DROP POLICY IF EXISTS "Service role full access" ON command_permissions;
CREATE POLICY "Service role full access" ON command_permissions FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON guild_roles;
CREATE POLICY "Service role full access" ON guild_roles FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON user_roles;
CREATE POLICY "Service role full access" ON user_roles FOR ALL USING (true);
DROP POLICY IF EXISTS "Service role full access" ON moderation_actions;
CREATE POLICY "Service role full access" ON moderation_actions FOR ALL USING (true);

-- =====================================================
-- SYNC FUNCTIONS
-- =====================================================

-- Function to atomically log transaction and update user balance
DROP FUNCTION IF EXISTS log_transaction_atomic;

CREATE FUNCTION log_transaction_atomic(
    p_guild_id TEXT,
    p_user_id TEXT,
    p_amount INTEGER,
    p_balance_before INTEGER,
    p_balance_after INTEGER,
    p_transaction_type TEXT,
    p_description TEXT,
    p_transaction_id TEXT,
    p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE(
    transaction_id TEXT,
    user_id TEXT,
    guild_id TEXT,
    amount INTEGER,
    balance_before INTEGER,
    balance_after INTEGER,
    transaction_type TEXT,
    description TEXT,
    metadata JSONB,
    "timestamp" TIMESTAMP WITH TIME ZONE
) AS $$
DECLARE
    v_timestamp TIMESTAMP WITH TIME ZONE;
BEGIN
    v_timestamp := NOW();
    
    INSERT INTO transactions (
        transaction_id,
        user_id,
        guild_id,
        amount,
        balance_before,
        balance_after,
        transaction_type,
        description,
        metadata,
        "timestamp"
    ) VALUES (
        p_transaction_id,
        p_user_id,
        p_guild_id,
        p_amount,
        p_balance_before,
        p_balance_after,
        p_transaction_type,
        p_description,
        p_metadata,
        v_timestamp
    );
    
    UPDATE users
    SET 
        balance = p_balance_after,
        total_earned = CASE WHEN p_amount > 0 THEN COALESCE(total_earned,0)+p_amount ELSE COALESCE(total_earned,0) END,
        total_spent = CASE WHEN p_amount < 0 THEN COALESCE(total_spent,0)+ABS(p_amount) ELSE COALESCE(total_spent,0) END,
        updated_at = v_timestamp
    WHERE users.user_id = p_user_id AND users.guild_id = p_guild_id;
    
    RETURN QUERY SELECT p_transaction_id, p_user_id, p_guild_id, p_amount, p_balance_before, p_balance_after, p_transaction_type, p_description, p_metadata, v_timestamp;
END;
$$ LANGUAGE plpgsql;

-- Function to sync guild last_sync timestamp
CREATE OR REPLACE FUNCTION sync_guild_last_sync(p_guild_id TEXT)
RETURNS VOID AS $$
BEGIN
    UPDATE guilds
    SET last_sync = NOW(), updated_at = NOW()
    WHERE guild_id = p_guild_id;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- INITIAL DATA
-- =====================================================

-- Create default admin user (password will be set by application)
INSERT INTO admin_users (username, password_hash, is_superadmin)
VALUES ('admin', 'temporary_will_be_replaced_on_first_login', true)
ON CONFLICT (username) DO NOTHING;

-- =====================================================
-- BALANCE MIGRATION & RECONCILIATION FUNCTIONS
-- =====================================================
-- These functions sync user balances from transactions table
-- (source of truth) to the users table for CMS display
-- =====================================================

-- Function to recalculate and show balance discrepancies
CREATE OR REPLACE FUNCTION recalculate_user_balances()
RETURNS TABLE(
    user_id TEXT,
    guild_id TEXT,
    current_balance INTEGER,
    calculated_balance INTEGER,
    discrepancy INTEGER,
    transaction_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH transaction_sums AS (
        SELECT 
            t.user_id,
            t.guild_id,
            SUM(t.amount) as total_amount,
            COUNT(*) as txn_count
        FROM transactions t
        GROUP BY t.user_id, t.guild_id
    )
    SELECT 
        u.user_id::TEXT,
        u.guild_id::TEXT,
        u.balance as current_balance,
        COALESCE(ts.total_amount, 0)::INTEGER as calculated_balance,
        (u.balance - COALESCE(ts.total_amount, 0))::INTEGER as discrepancy,
        COALESCE(ts.txn_count, 0) as transaction_count
    FROM users u
    LEFT JOIN transaction_sums ts 
        ON u.user_id = ts.user_id 
        AND u.guild_id = ts.guild_id
    WHERE u.balance != COALESCE(ts.total_amount, 0);
END;
$$ LANGUAGE plpgsql;

-- Function to sync all user balances from transactions
CREATE OR REPLACE FUNCTION sync_all_user_balances()
RETURNS TABLE(
    users_updated INTEGER,
    total_discrepancy BIGINT
) AS $$
DECLARE
    v_users_updated INTEGER;
    v_total_discrepancy BIGINT;
BEGIN
    -- Calculate total discrepancy before fix
    SELECT SUM(ABS(u.balance - COALESCE(ts.total_amount, 0)))
    INTO v_total_discrepancy
    FROM users u
    LEFT JOIN (
        SELECT user_id, guild_id, SUM(amount) as total_amount
        FROM transactions
        GROUP BY user_id, guild_id
    ) ts ON u.user_id = ts.user_id AND u.guild_id = ts.guild_id;
    
    -- Update all user balances from transactions
    WITH transaction_sums AS (
        SELECT 
            user_id,
            guild_id,
            SUM(amount) as total_amount,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_earned,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_spent
        FROM transactions
        GROUP BY user_id, guild_id
    )
    UPDATE users u
    SET 
        balance = COALESCE(ts.total_amount, 0),
        total_earned = COALESCE(ts.total_earned, 0),
        total_spent = COALESCE(ts.total_spent, 0),
        updated_at = NOW()
    FROM transaction_sums ts
    WHERE u.user_id = ts.user_id 
      AND u.guild_id = ts.guild_id
      AND u.balance != COALESCE(ts.total_amount, 0);
    
    GET DIAGNOSTICS v_users_updated = ROW_COUNT;
    
    RETURN QUERY SELECT v_users_updated, COALESCE(v_total_discrepancy, 0);
END;
$$ LANGUAGE plpgsql;

-- Function to sync a specific user's balance
CREATE OR REPLACE FUNCTION sync_user_balance(
    p_user_id TEXT,
    p_guild_id TEXT
)
RETURNS TABLE(
    old_balance INTEGER,
    new_balance INTEGER,
    difference INTEGER
) AS $$
DECLARE
    v_old_balance INTEGER;
    v_new_balance INTEGER;
BEGIN
    -- Get current balance
    SELECT balance INTO v_old_balance
    FROM users
    WHERE user_id = p_user_id AND guild_id = p_guild_id;
    
    -- Calculate correct balance from transactions
    SELECT COALESCE(SUM(amount), 0) INTO v_new_balance
    FROM transactions
    WHERE user_id = p_user_id AND guild_id = p_guild_id;
    
    -- Update user balance
    UPDATE users
    SET 
        balance = v_new_balance,
        total_earned = COALESCE((
            SELECT SUM(amount) FROM transactions 
            WHERE user_id = p_user_id AND guild_id = p_guild_id AND amount > 0
        ), 0),
        total_spent = COALESCE((
            SELECT SUM(ABS(amount)) FROM transactions 
            WHERE user_id = p_user_id AND guild_id = p_guild_id AND amount < 0
        ), 0),
        updated_at = NOW()
    WHERE user_id = p_user_id AND guild_id = p_guild_id;
    
    RETURN QUERY SELECT 
        COALESCE(v_old_balance, 0),
        v_new_balance,
        COALESCE(v_old_balance, 0) - v_new_balance;
END;
$$ LANGUAGE plpgsql;

-- Function to validate balance integrity
CREATE OR REPLACE FUNCTION validate_balance_integrity()
RETURNS TABLE(
    total_users BIGINT,
    users_with_discrepancies BIGINT,
    total_discrepancy BIGINT,
    max_discrepancy INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH balance_check AS (
        SELECT 
            u.user_id,
            u.guild_id,
            u.balance,
            COALESCE(SUM(t.amount), 0) as calculated_balance,
            ABS(u.balance - COALESCE(SUM(t.amount), 0)) as discrepancy
        FROM users u
        LEFT JOIN transactions t 
            ON u.user_id = t.user_id AND u.guild_id = t.guild_id
        GROUP BY u.user_id, u.guild_id, u.balance
    )
    SELECT 
        COUNT(*)::BIGINT as total_users,
        COUNT(CASE WHEN discrepancy > 0 THEN 1 END)::BIGINT as users_with_discrepancies,
        COALESCE(SUM(discrepancy), 0)::BIGINT as total_discrepancy,
        COALESCE(MAX(discrepancy), 0)::INTEGER as max_discrepancy
    FROM balance_check;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- AD VIEWS TABLE (Monetag Ad Tracking)
-- =====================================================
CREATE TABLE IF NOT EXISTS ad_views (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    
    -- Ad details
    ad_type TEXT DEFAULT 'monetag_interstitial',
    ad_session_id TEXT UNIQUE NOT NULL,
    
    -- Verification
    is_verified BOOLEAN DEFAULT false,
    verified_at TIMESTAMP WITH TIME ZONE,
    ip_address TEXT,
    user_agent TEXT,
    
    -- Reward tracking
    reward_amount INTEGER DEFAULT 10,
    reward_granted BOOLEAN DEFAULT false,
    transaction_id TEXT,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- =====================================================
-- GLOBAL TASKS TABLE (Cross-Server Permanent Tasks)
-- =====================================================
CREATE TABLE IF NOT EXISTS global_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_key TEXT UNIQUE NOT NULL,  -- e.g., 'ad_claim_task'
    
    -- Task details
    name TEXT NOT NULL,
    description TEXT,
    reward INTEGER NOT NULL CHECK (reward > 0),
    
    -- Task type
    task_type TEXT DEFAULT 'ad_claim' CHECK (task_type IN ('ad_claim', 'daily', 'special')),
    
    -- Configuration
    is_active BOOLEAN DEFAULT true,
    is_repeatable BOOLEAN DEFAULT true,  -- Can be claimed multiple times
    cooldown_minutes INTEGER DEFAULT 0,  -- Cooldown between claims (0 = no cooldown)
    
    -- Display
    icon_emoji TEXT DEFAULT '🎁',
    button_text TEXT DEFAULT 'Claim Here',
    disclaimer TEXT,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- GLOBAL TASK CLAIMS TABLE (User Claims for Global Tasks)
-- =====================================================
CREATE TABLE IF NOT EXISTS global_task_claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    task_key TEXT NOT NULL,
    
    -- Claim details
    claimed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Ad session link (for ad_claim tasks)
    ad_session_id TEXT,
    
    -- Reward tracking
    reward_amount INTEGER NOT NULL,
    reward_granted BOOLEAN DEFAULT false,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

-- =====================================================
-- INDEXES FOR AD TRACKING
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_ad_views_user ON ad_views(user_id);
CREATE INDEX IF NOT EXISTS idx_ad_views_guild ON ad_views(guild_id);
CREATE INDEX IF NOT EXISTS idx_ad_views_session ON ad_views(ad_session_id);
CREATE INDEX IF NOT EXISTS idx_ad_views_verified ON ad_views(is_verified, verified_at);
CREATE INDEX IF NOT EXISTS idx_ad_views_created ON ad_views(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_global_tasks_active ON global_tasks(is_active);
CREATE INDEX IF NOT EXISTS idx_global_tasks_type ON global_tasks(task_type);

CREATE INDEX IF NOT EXISTS idx_global_task_claims_user ON global_task_claims(user_id, guild_id);
CREATE INDEX IF NOT EXISTS idx_global_task_claims_task ON global_task_claims(task_key);
CREATE INDEX IF NOT EXISTS idx_global_task_claims_session ON global_task_claims(ad_session_id);
CREATE INDEX IF NOT EXISTS idx_global_task_claims_claimed ON global_task_claims(claimed_at DESC);

-- =====================================================
-- TRIGGERS FOR AD TRACKING TABLES
-- =====================================================
DROP TRIGGER IF EXISTS update_global_tasks_updated_at ON global_tasks;
CREATE TRIGGER update_global_tasks_updated_at
BEFORE UPDATE ON global_tasks
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- ROW LEVEL SECURITY FOR AD TRACKING
-- =====================================================
ALTER TABLE ad_views ENABLE ROW LEVEL SECURITY;
ALTER TABLE global_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE global_task_claims ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access" ON ad_views;
CREATE POLICY "Service role full access" ON ad_views FOR ALL USING (true);

DROP POLICY IF EXISTS "Service role full access" ON global_tasks;
CREATE POLICY "Service role full access" ON global_tasks FOR ALL USING (true);

DROP POLICY IF EXISTS "Service role full access" ON global_task_claims;
CREATE POLICY "Service role full access" ON global_task_claims FOR ALL USING (true);

-- =====================================================
-- INSERT DEFAULT GLOBAL AD CLAIM TASK
-- =====================================================
INSERT INTO global_tasks (
    task_key,
    name,
    description,
    reward,
    task_type,
    is_active,
    is_repeatable,
    cooldown_minutes,
    icon_emoji,
    button_text,
    disclaimer
) VALUES (
    'ad_claim_task',
    'Claim For 10 Free Points',
    'Watch these ads for 10 points',
    10,
    'ad_claim',
    true,
    true,
    0,
    '🎁',
    'Claim Here',
    'Please note that the ads displayed are from third-party networks (like Monetag). We have no control over the content of these advertisements and are not affiliated with, nor do we endorse, any claims made within them.'
) ON CONFLICT (task_key) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    reward = EXCLUDED.reward,
    disclaimer = EXCLUDED.disclaimer,
    updated_at = NOW();

-- =====================================================
-- USAGE INSTRUCTIONS
-- =====================================================
-- 
-- To check for balance discrepancies:
--   SELECT * FROM recalculate_user_balances();
--
-- To sync all user balances:
--   SELECT * FROM sync_all_user_balances();
--
-- To sync a specific user:
--   SELECT * FROM sync_user_balance('USER_ID', 'GUILD_ID');
--
-- To validate overall integrity:
--   SELECT * FROM validate_balance_integrity();
--
-- To view ad statistics:
--   SELECT user_id, COUNT(*) as total_views, SUM(CASE WHEN is_verified THEN 1 ELSE 0 END) as verified_views
--   FROM ad_views GROUP BY user_id ORDER BY total_views DESC;
--
-- =====================================================
