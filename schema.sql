-- =====================================================
-- SUPER SCHEMA FOR EVL DISCORD BOT (Consolidated)
-- Includes all core tables, security extensions, and RPC functions.
-- Designed for Supabase (PostgreSQL 14+)
-- =====================================================

-- 0. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. BASE UTILS
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 2. CORE SYSTEM & AUTHENTICATION
-- =====================================================

-- GUILDS table
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
    subscription_tier TEXT DEFAULT 'free',
    subscription_expiry TIMESTAMPTZ,

    -- Boost Rewards
    boost_reward_enabled BOOLEAN DEFAULT true,
    boost_reward_amount INTEGER DEFAULT 1000,
    boost_log_channel_id TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_synced TIMESTAMP WITH TIME ZONE
);

-- ADMIN USERS (CMS Access)
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username TEXT UNIQUE,
    password_hash TEXT,  -- Nullable for Discord OAuth
    discord_id TEXT UNIQUE,
    discord_username TEXT,
    discord_avatar TEXT,
    discord_access_token TEXT,
    discord_refresh_token TEXT,
    discord_token_expires_at TIMESTAMPTZ,
    allowed_guild_ids TEXT[], 
    is_superadmin BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- WEB SESSIONS (CMS Sessions)
CREATE TABLE IF NOT EXISTS web_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    user_data JSONB,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    max_expires_at TIMESTAMP WITH TIME ZONE,
    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_permission_check TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address TEXT,
    user_agent TEXT,
    is_valid BOOLEAN DEFAULT true
);

-- DISCORD OAUTH LOGS
CREATE TABLE IF NOT EXISTS discord_oauth_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    discord_id TEXT,
    action TEXT,
    ip_address TEXT,
    guilds_synced TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- 3. ECONOMY & USER DATA
-- =====================================================

-- USERS table
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

-- Ensure balance constraint
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT users_balance_non_negative CHECK (balance >= 0);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- DAILY CLAIMS (Idempotency)
CREATE TABLE IF NOT EXISTS daily_claims (
    guild_id    TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    claim_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    reward      NUMERIC NOT NULL DEFAULT 100,
    claimed_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id, claim_date)
);

-- TRANSACTIONS table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT,
    amount NUMERIC NOT NULL,
    balance_before NUMERIC,
    balance_after NUMERIC,
    transaction_type TEXT,
    description TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    "timestamp" TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- SHOP ITEMS table
CREATE TABLE IF NOT EXISTS shop_items (
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    item_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    price NUMERIC NOT NULL CHECK (price >= 0),
    category TEXT DEFAULT 'general',
    stock INTEGER DEFAULT -1,
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
    item_id TEXT,
    quantity INTEGER DEFAULT 1 CHECK (quantity >= 0),
    acquired_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id, item_id)
);

-- =====================================================
-- 4. TASKS & MODERATION
-- =====================================================

-- TASKS table
CREATE TABLE IF NOT EXISTS tasks (
    task_id BIGINT,
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    reward NUMERIC NOT NULL CHECK (reward >= 0),
    duration_hours INTEGER DEFAULT 24,
    status TEXT DEFAULT 'active',
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

-- USER TASKS table
CREATE TABLE IF NOT EXISTS user_tasks (
    guild_id TEXT,
    user_id TEXT,
    task_id BIGINT,
    status TEXT DEFAULT 'in_progress',
    claimed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deadline TIMESTAMP WITH TIME ZONE,
    proof_content TEXT,
    proof_message_id TEXT,
    proof_attachments JSONB DEFAULT '[]'::jsonb,
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    notes TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    submission_attempts INTEGER DEFAULT 0,
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

-- MODERATION ACTIONS table
CREATE TABLE IF NOT EXISTS moderation_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    moderator_id TEXT NOT NULL,
    action_type TEXT NOT NULL, -- warn, mute, kick, ban, unban, unmute, clear
    reason TEXT,
    duration INTEGER, -- in minutes, nulll for permanent
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- 5. FEATURES: GIVEAWAYS, BOOSTS, ANNOUNCEMENTS
-- =====================================================

-- GIVEAWAYS table
CREATE TABLE IF NOT EXISTS giveaways (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    guild_id text NOT NULL,
    created_by text NOT NULL,
    prize_source text NOT NULL,
    shop_item_id text,
    prize_name text NOT NULL,
    prize_description text,
    prize_image_url text,
    winner_count integer NOT NULL DEFAULT 1,
    entry_mode text NOT NULL,
    required_role_ids text[],
    raffle_cost integer,
    raffle_max_tickets_per_user integer DEFAULT 10,
    tag_role_id text,
    custom_message text,
    channel_id text NOT NULL,
    message_id text,
    status text NOT NULL DEFAULT 'active',
    start_at timestamptz,
    ends_at timestamptz NOT NULL,
    ended_at timestamptz,
    winner_user_ids text[] DEFAULT '{}',
    past_winners text[] DEFAULT '{}', -- Track winners from previous draws for this ID
    total_entries integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- GIVEAWAY ENTRIES table
CREATE TABLE IF NOT EXISTS giveaway_entries (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    giveaway_id uuid NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
    guild_id text NOT NULL,
    user_id text NOT NULL,
    tickets integer NOT NULL DEFAULT 1,
    amount_spent integer NOT NULL DEFAULT 0,
    entered_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(giveaway_id, user_id)
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

-- CHANNEL LOCK SCHEDULES table
CREATE TABLE IF NOT EXISTS channel_schedules (
    schedule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    is_enabled BOOLEAN DEFAULT true,
    unlock_time TIME NOT NULL,
    lock_time TIME NOT NULL,
    timezone TEXT DEFAULT 'America/New_York',
    active_days INTEGER[] DEFAULT ARRAY[0, 1, 2, 3, 4, 5, 6],
    current_state TEXT DEFAULT 'locked' CHECK (current_state IN ('locked', 'unlocked', 'error')),
    last_state_change TIMESTAMPTZ,
    last_error TEXT,
    original_permissions JSONB,
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(guild_id, channel_id)
);

-- TOP.GG VOTES table
CREATE TABLE IF NOT EXISTS topgg_votes (
    user_id TEXT,
    guild_id TEXT,
    voted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_weekend BOOLEAN DEFAULT false,
    query_params JSONB DEFAULT '{}'::jsonb,
    PRIMARY KEY (user_id, voted_at)
);

-- =====================================================
-- 6. RPC FUNCTIONS (Atomic Transactions)
-- =====================================================

-- RPC: process_balance_change
CREATE OR REPLACE FUNCTION process_balance_change(
    p_guild_id          TEXT,
    p_user_id           TEXT,
    p_amount            NUMERIC,
    p_transaction_type  TEXT,
    p_description       TEXT,
    p_metadata          JSONB DEFAULT '{}'::jsonb
) RETURNS TABLE (
    new_balance         NUMERIC,
    transaction_id      UUID,
    balance_before      NUMERIC,
    balance_after       NUMERIC,
    "timestamp"         TIMESTAMPTZ
) AS $$
DECLARE
    v_balance_before    NUMERIC;
    v_balance_after     NUMERIC;
    v_txn_id            UUID;
    v_now               TIMESTAMPTZ := NOW();
BEGIN
    SELECT balance INTO v_balance_before FROM users WHERE guild_id = p_guild_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO users (guild_id, user_id, balance, total_earned, total_spent, is_active)
        VALUES (p_guild_id, p_user_id, 0, 0, 0, true);
        v_balance_before := 0;
    END IF;
    v_balance_after := v_balance_before + p_amount;
    IF v_balance_after < 0 THEN RAISE EXCEPTION 'Insufficient balance'; END IF;
    v_txn_id := uuid_generate_v4();
    INSERT INTO transactions (transaction_id, guild_id, user_id, amount, balance_before, balance_after, transaction_type, description, metadata, "timestamp")
    VALUES (v_txn_id, p_guild_id, p_user_id, p_amount, v_balance_before, v_balance_after, p_transaction_type, p_description, p_metadata, v_now);
    UPDATE users SET balance = v_balance_after, total_earned = CASE WHEN p_amount > 0 THEN total_earned + p_amount ELSE total_earned END,
        total_spent = CASE WHEN p_amount < 0 THEN total_spent + ABS(p_amount) ELSE total_spent END, updated_at = v_now
    WHERE guild_id = p_guild_id AND user_id = p_user_id;
    RETURN QUERY SELECT v_balance_after, v_txn_id, v_balance_before, v_balance_after, v_now;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: claim_daily_reward
CREATE OR REPLACE FUNCTION claim_daily_reward(p_guild_id TEXT, p_user_id TEXT, p_reward NUMERIC DEFAULT 100)
RETURNS TABLE (success BOOLEAN, new_balance NUMERIC, already_claimed BOOLEAN, transaction_id UUID, next_claim_at TIMESTAMPTZ) AS $$
DECLARE
    v_balance NUMERIC;
    v_txn_id UUID;
    v_now TIMESTAMPTZ := NOW();
BEGIN
    INSERT INTO daily_claims (guild_id, user_id, claim_date, reward, claimed_at) VALUES (p_guild_id, p_user_id, CURRENT_DATE, p_reward, v_now) ON CONFLICT DO NOTHING;
    IF NOT FOUND THEN RETURN QUERY SELECT false, 0::NUMERIC, true, NULL::UUID, (CURRENT_DATE + INTERVAL '1 day')::TIMESTAMPTZ; RETURN; END IF;
    SELECT * INTO v_txn_id FROM process_balance_change(p_guild_id, p_user_id, p_reward, 'daily_reward', 'Daily reward');
    SELECT balance INTO v_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_user_id;
    RETURN QUERY SELECT true, v_balance, false, v_txn_id, (CURRENT_DATE + INTERVAL '1 day')::TIMESTAMPTZ;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: claim_monthly_boost_reward
CREATE OR REPLACE FUNCTION claim_monthly_boost_reward(p_guild_id TEXT, p_user_id TEXT, p_amount NUMERIC) RETURNS JSONB AS $$
DECLARE
    v_updated_count INT;
    v_res RECORD;
BEGIN
    UPDATE server_boosts SET last_reward_at = NOW(), updated_at = NOW()
    WHERE guild_id = p_guild_id AND user_id = p_user_id AND is_active = True AND (unboosted_at IS NULL)
      AND (last_reward_at IS NULL OR last_reward_at < NOW() - INTERVAL '30 days');
    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    IF v_updated_count = 0 THEN RETURN jsonb_build_object('success', false, 'error', 'Not due for reward'); END IF;
    SELECT * INTO v_res FROM process_balance_change(p_guild_id, p_user_id, p_amount, 'boost_reward', 'Monthly server boost reward');
    RETURN jsonb_build_object('success', true, 'new_balance', v_res.new_balance, 'transaction_id', v_res.transaction_id);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: purchase_item_atomic
CREATE OR REPLACE FUNCTION purchase_item_atomic(p_guild_id TEXT, p_user_id TEXT, p_item_id TEXT, p_quantity INTEGER) RETURNS JSONB AS $$
DECLARE
    v_item_price NUMERIC;
    v_item_name TEXT;
    v_res RECORD;
BEGIN
    SELECT price, name INTO v_item_price, v_item_name FROM shop_items WHERE guild_id = p_guild_id AND item_id = p_item_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success', false, 'error', 'Item not found'); END IF;
    SELECT * INTO v_res FROM process_balance_change(p_guild_id, p_user_id, -(v_item_price * p_quantity), 'shop_purchase', 'Purchased ' || v_item_name);
    INSERT INTO inventory (guild_id, user_id, item_id, quantity) VALUES (p_guild_id, p_user_id, p_item_id, p_quantity)
    ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity, updated_at = NOW();
    RETURN jsonb_build_object('success', true, 'new_balance', v_res.new_balance, 'transaction_id', v_res.transaction_id);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: enter_raffle_giveaway
CREATE OR REPLACE FUNCTION enter_raffle_giveaway(p_giveaway_id UUID, p_guild_id TEXT, p_user_id TEXT, p_tickets INTEGER, p_cost INTEGER) RETURNS JSONB AS $$
DECLARE
    v_res RECORD;
BEGIN
    SELECT * INTO v_res FROM process_balance_change(p_guild_id, p_user_id, -p_cost, 'giveaway_entry', 'Raffle entry');
    INSERT INTO giveaway_entries (giveaway_id, guild_id, user_id, tickets, amount_spent)
    VALUES (p_giveaway_id, p_guild_id, p_user_id, p_tickets, p_cost)
    ON CONFLICT (giveaway_id, user_id) DO UPDATE SET tickets = giveaway_entries.tickets + EXCLUDED.tickets, amount_spent = giveaway_entries.amount_spent + EXCLUDED.amount_spent;
    UPDATE giveaways SET total_entries = total_entries + p_tickets WHERE id = p_giveaway_id;
    RETURN jsonb_build_object('success', true, 'new_balance', v_res.new_balance);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: upsert_discord_user
CREATE OR REPLACE FUNCTION upsert_discord_user(p_discord_id TEXT, p_discord_username TEXT, p_discord_avatar TEXT, p_access_token TEXT, p_refresh_token TEXT, p_token_expires_at TIMESTAMPTZ, p_owned_guild_ids TEXT[]) RETURNS UUID AS $$
DECLARE
    v_user_id UUID;
BEGIN
    INSERT INTO admin_users (discord_id, discord_username, discord_avatar, discord_access_token, discord_refresh_token, discord_token_expires_at, allowed_guild_ids, username)
    VALUES (p_discord_id, p_discord_username, p_discord_avatar, p_access_token, p_refresh_token, p_token_expires_at, p_owned_guild_ids, p_discord_username)
    ON CONFLICT (discord_id) DO UPDATE SET discord_username = EXCLUDED.discord_username, discord_avatar = EXCLUDED.discord_avatar, discord_access_token = EXCLUDED.discord_access_token,
        discord_refresh_token = EXCLUDED.discord_refresh_token, discord_token_expires_at = EXCLUDED.discord_token_expires_at, allowed_guild_ids = EXCLUDED.allowed_guild_ids, last_login = NOW(), updated_at = NOW()
    RETURNING id INTO v_user_id;
    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: sync_discord_user_guilds
CREATE OR REPLACE FUNCTION sync_discord_user_guilds(p_discord_id TEXT, p_owned_guild_ids TEXT[]) RETURNS VOID AS $$
BEGIN
    UPDATE admin_users SET allowed_guild_ids = p_owned_guild_ids, updated_at = NOW() WHERE discord_id = p_discord_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: expire_overdue_tasks
CREATE OR REPLACE FUNCTION expire_overdue_tasks() RETURNS INTEGER AS $$
DECLARE
    expired_tasks_count INTEGER := 0;
    expired_user_tasks_count INTEGER := 0;
BEGIN
    WITH ut AS (UPDATE user_tasks SET status = 'expired', updated_at = NOW() WHERE status = 'in_progress' AND deadline < NOW() RETURNING guild_id)
    SELECT count(*) INTO expired_user_tasks_count FROM ut;
    WITH t AS (UPDATE tasks SET status = 'expired', updated_at = NOW() WHERE status = 'active' AND expires_at < NOW() RETURNING task_id)
    SELECT count(*) INTO expired_tasks_count FROM t;
    RETURN expired_tasks_count + expired_user_tasks_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: increment_giveaway_entries
CREATE OR REPLACE FUNCTION increment_giveaway_entries(g_id uuid, t_count integer) RETURNS void AS $$
BEGIN
    UPDATE giveaways SET total_entries = total_entries + t_count WHERE id = g_id;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions for NEW functions
GRANT EXECUTE ON FUNCTION expire_overdue_tasks TO anon;
GRANT EXECUTE ON FUNCTION increment_giveaway_entries TO anon;

-- =====================================================
-- 7. TRIGGERS & PERMISSIONS
-- =====================================================

-- Timestamps
DROP TRIGGER IF EXISTS update_guilds_updated_at ON guilds;
CREATE TRIGGER update_guilds_updated_at BEFORE UPDATE ON guilds FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_shop_items_updated_at ON shop_items;
CREATE TRIGGER update_shop_items_updated_at BEFORE UPDATE ON shop_items FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_inventory_updated_at ON inventory;
CREATE TRIGGER update_inventory_updated_at BEFORE UPDATE ON inventory FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tasks_updated_at ON tasks;
CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_tasks_updated_at ON user_tasks;
CREATE TRIGGER update_user_tasks_updated_at BEFORE UPDATE ON user_tasks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_task_settings_updated_at ON task_settings;
CREATE TRIGGER update_task_settings_updated_at BEFORE UPDATE ON task_settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_embeds_updated_at ON embeds;
CREATE TRIGGER update_embeds_updated_at BEFORE UPDATE ON embeds FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_server_boosts_updated_at ON server_boosts;
CREATE TRIGGER update_server_boosts_updated_at BEFORE UPDATE ON server_boosts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS channel_schedules_timestamp ON channel_schedules;
CREATE TRIGGER channel_schedules_timestamp BEFORE UPDATE ON channel_schedules FOR EACH ROW EXECUTE FUNCTION update_channel_schedules_timestamp();

-- Grant Public Action permissions
GRANT EXECUTE ON FUNCTION process_balance_change TO anon;
GRANT EXECUTE ON FUNCTION claim_daily_reward TO anon;
GRANT EXECUTE ON FUNCTION claim_monthly_boost_reward TO anon;
GRANT EXECUTE ON FUNCTION purchase_item_atomic TO anon;
GRANT EXECUTE ON FUNCTION enter_raffle_giveaway TO anon;
GRANT EXECUTE ON FUNCTION upsert_discord_user TO anon;
GRANT EXECUTE ON FUNCTION sync_discord_user_guilds TO anon;

-- Row Level Security (Generally enabled but permissive for bot service role)
ALTER TABLE guilds ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE shop_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE moderation_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE giveaways ENABLE ROW LEVEL SECURITY;
ALTER TABLE giveaway_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE web_sessions ENABLE ROW LEVEL SECURITY;

-- Allow all for now (managed by service role)
DROP POLICY IF EXISTS "Public Full Access" ON guilds;
CREATE POLICY "Public Full Access" ON guilds FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON users;
CREATE POLICY "Public Full Access" ON users FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON shop_items;
CREATE POLICY "Public Full Access" ON shop_items FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON giveaways;
CREATE POLICY "Public Full Access" ON giveaways FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON web_sessions;
CREATE POLICY "Public Full Access" ON web_sessions FOR ALL USING (true);

-- Comments
COMMENT ON TABLE guilds IS 'Core Discord server configuration';
COMMENT ON TABLE users IS 'Economy and user state';
COMMENT ON TABLE web_sessions IS 'CMS authentication sessions with TTL and re-validation hardening';
COMMENT ON TABLE moderation_actions IS 'Persistent audit log for all manual and automated moderation';
COMMENT ON TABLE giveaways IS 'Server giveaway state with streak-aware winner tracking';
