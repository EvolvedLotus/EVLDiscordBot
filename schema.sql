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

-- ARCHIVED SHOP ITEMS table
CREATE TABLE IF NOT EXISTS archived_shop_items (
    guild_id    TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    price       NUMERIC NOT NULL,
    category    TEXT DEFAULT 'general',
    emoji       TEXT DEFAULT '🛍️',
    role_id     TEXT,
    duration_minutes INTEGER,
    metadata    JSONB DEFAULT '{}'::jsonb,
    archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    archived_by TEXT,
    PRIMARY KEY (guild_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_archived_shop_items_guild ON archived_shop_items(guild_id);

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

-- STRIKES table
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

-- MODERATION ACTIONS table
CREATE TABLE IF NOT EXISTS moderation_actions (
    id SERIAL PRIMARY KEY,
    action_id TEXT UNIQUE NOT NULL,
    guild_id TEXT REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    action_type TEXT NOT NULL, -- warn, mute, kick, ban, unban, unmute, clear
    reason TEXT,
    moderator_id TEXT NOT NULL,
    duration_seconds INTEGER,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mod_actions_guild ON moderation_actions(guild_id, user_id, action_type);

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

-- AD VIEWS table
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
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ad_views_user ON ad_views(user_id);
CREATE INDEX IF NOT EXISTS idx_ad_views_created_at ON ad_views(created_at);
CREATE INDEX IF NOT EXISTS idx_ad_views_expires ON ad_views(expires_at);

-- CUSTOM ADS table (Railway PG / Supabase)
CREATE TABLE IF NOT EXISTS custom_ads (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    headline TEXT,
    cta TEXT DEFAULT 'Learn More',
    url TEXT NOT NULL,
    image TEXT,
    ad_type TEXT DEFAULT 'static',
    color TEXT DEFAULT '#007bff',
    is_active BOOLEAN DEFAULT true,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- AD CLIENTS table (Railway PG / Supabase)
CREATE TABLE IF NOT EXISTS ad_clients (
    client_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    weight INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT true,
    last_request_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- GLOBAL TASKS table
CREATE TABLE IF NOT EXISTS global_tasks (
    task_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    reward_amount NUMERIC DEFAULT 10,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- GLOBAL TASK CLAIMS table
CREATE TABLE IF NOT EXISTS global_task_claims (
    claim_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    task_key TEXT NOT NULL REFERENCES global_tasks(task_key),
    ad_session_id TEXT REFERENCES ad_views(ad_session_id),
    reward_amount NUMERIC DEFAULT 10,
    reward_granted BOOLEAN DEFAULT false,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_global_task_claims_user ON global_task_claims(user_id);

-- TOP.GG VOTE LOGS TABLE
CREATE TABLE IF NOT EXISTS vote_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    vote_type TEXT NOT NULL, -- 'bot' or 'server'
    target_id TEXT NOT NULL, -- bot ID or server ID that was voted for
    reward INTEGER NOT NULL DEFAULT 100,
    is_weekend BOOLEAN DEFAULT false,
    platform TEXT DEFAULT 'topgg',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vote_logs_user_id ON vote_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_vote_logs_created_at ON vote_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_vote_logs_user_recent ON vote_logs(user_id, created_at DESC);

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

-- RPC: process_transfer
CREATE OR REPLACE FUNCTION process_transfer(
    p_guild_id          TEXT,
    p_sender_id         TEXT,
    p_receiver_id       TEXT,
    p_amount            NUMERIC,
    p_description_send  TEXT,
    p_description_recv  TEXT,
    p_metadata_send     JSONB DEFAULT '{}'::jsonb,
    p_metadata_recv     JSONB DEFAULT '{}'::jsonb
) RETURNS TABLE (
    sender_new_balance      NUMERIC,
    receiver_new_balance    NUMERIC,
    send_transaction_id     UUID,
    recv_transaction_id     UUID,
    sender_balance_before   NUMERIC,
    receiver_balance_before NUMERIC
) AS $$
DECLARE
    v_sender_balance        NUMERIC;
    v_receiver_balance      NUMERIC;
    v_sender_new            NUMERIC;
    v_receiver_new          NUMERIC;
    v_send_txn_id           UUID;
    v_recv_txn_id           UUID;
    v_now                   TIMESTAMPTZ := NOW();
BEGIN
    IF p_sender_id < p_receiver_id THEN
        SELECT balance INTO v_sender_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_sender_id FOR UPDATE;
        SELECT balance INTO v_receiver_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_receiver_id FOR UPDATE;
    ELSE
        SELECT balance INTO v_receiver_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_receiver_id FOR UPDATE;
        SELECT balance INTO v_sender_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_sender_id FOR UPDATE;
    END IF;
    IF v_sender_balance IS NULL THEN RAISE EXCEPTION 'Sender account not found'; END IF;
    IF v_receiver_balance IS NULL THEN
        INSERT INTO users (guild_id, user_id, balance, total_earned, total_spent, is_active)
        VALUES (p_guild_id, p_receiver_id, 0, 0, 0, true);
        v_receiver_balance := 0;
    END IF;
    v_sender_new := v_sender_balance - p_amount;
    v_receiver_new := v_receiver_balance + p_amount;
    IF v_sender_new < 0 THEN RAISE EXCEPTION 'Insufficient balance'; END IF;
    v_send_txn_id := uuid_generate_v4();
    v_recv_txn_id := uuid_generate_v4();
    INSERT INTO transactions (transaction_id, guild_id, user_id, amount, balance_before, balance_after, transaction_type, description, metadata, "timestamp")
    VALUES (v_send_txn_id, p_guild_id, p_sender_id, -p_amount, v_sender_balance, v_sender_new, 'transfer_sent', p_description_send, p_metadata_send, v_now);
    INSERT INTO transactions (transaction_id, guild_id, user_id, amount, balance_before, balance_after, transaction_type, description, metadata, "timestamp")
    VALUES (v_recv_txn_id, p_guild_id, p_receiver_id, p_amount, v_receiver_balance, v_receiver_new, 'transfer_received', p_description_recv, p_metadata_recv, v_now);
    UPDATE users SET balance = v_sender_new, total_spent = total_spent + p_amount, updated_at = v_now WHERE guild_id = p_guild_id AND user_id = p_sender_id;
    UPDATE users SET balance = v_receiver_new, total_earned = total_earned + p_amount, updated_at = v_now WHERE guild_id = p_guild_id AND user_id = p_receiver_id;
    RETURN QUERY SELECT v_sender_new, v_receiver_new, v_send_txn_id, v_recv_txn_id, v_sender_balance, v_receiver_balance;
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
    RETURN jsonb_build_object('success', true, 'new_balance', v_res.new_balance, 'transaction_id', v_res.transaction_id, 'balance_before', v_res.balance_before, 'balance_after', v_res.balance_after);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: process_purchase
CREATE OR REPLACE FUNCTION process_purchase(
    p_guild_id      TEXT,
    p_user_id       TEXT,
    p_item_id       TEXT,
    p_quantity       INTEGER,
    p_expected_price NUMERIC DEFAULT NULL
) RETURNS TABLE (
    success          BOOLEAN,
    error_message    TEXT,
    new_balance      NUMERIC,
    new_stock        INTEGER,
    inventory_total  INTEGER,
    total_cost       NUMERIC,
    transaction_id   UUID,
    item_name        TEXT,
    item_emoji       TEXT,
    actual_price     NUMERIC
) AS $$
DECLARE
    v_item           RECORD;
    v_user_balance   NUMERIC;
    v_total_cost     NUMERIC;
    v_new_balance    NUMERIC;
    v_new_stock      INTEGER;
    v_current_inv    INTEGER;
    v_new_inv        INTEGER;
    v_txn_id         UUID;
    v_now            TIMESTAMPTZ := NOW();
BEGIN
    SELECT name, price, stock, is_active, emoji INTO v_item FROM shop_items WHERE guild_id = p_guild_id AND item_id = p_item_id FOR UPDATE;
    IF NOT FOUND THEN RETURN QUERY SELECT false, 'Item not found'::TEXT, 0::NUMERIC, 0::INTEGER, 0::INTEGER, 0::NUMERIC, NULL::UUID, ''::TEXT, ''::TEXT, 0::NUMERIC; RETURN; END IF;
    IF NOT v_item.is_active THEN RETURN QUERY SELECT false, 'Item is not active'::TEXT, 0::NUMERIC, 0::INTEGER, 0::INTEGER, 0::NUMERIC, NULL::UUID, ''::TEXT, ''::TEXT, 0::NUMERIC; RETURN; END IF;
    IF p_expected_price IS NOT NULL AND p_expected_price != v_item.price THEN RETURN QUERY SELECT false, 'Price mismatch'::TEXT, 0::NUMERIC, 0::INTEGER, 0::INTEGER, 0::NUMERIC, NULL::UUID, v_item.name, v_item.emoji, v_item.price; RETURN; END IF;
    IF v_item.stock != -1 AND v_item.stock < p_quantity THEN RETURN QUERY SELECT false, 'Insufficient stock'::TEXT, 0::NUMERIC, v_item.stock, 0::INTEGER, 0::NUMERIC, NULL::UUID, v_item.name, v_item.emoji, v_item.price; RETURN; END IF;
    v_total_cost := v_item.price * p_quantity;
    SELECT balance INTO v_user_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN INSERT INTO users (guild_id, user_id, balance, total_earned, total_spent, is_active) VALUES (p_guild_id, p_user_id, 0, 0, 0, true); v_user_balance := 0; END IF;
    v_new_balance := v_user_balance - v_total_cost;
    IF v_new_balance < 0 THEN RETURN QUERY SELECT false, 'Insufficient balance'::TEXT, v_user_balance, 0::INTEGER, 0::INTEGER, v_total_cost, NULL::UUID, v_item.name, v_item.emoji, v_item.price; RETURN; END IF;
    v_txn_id := uuid_generate_v4();
    UPDATE users SET balance = v_new_balance, total_spent = total_spent + v_total_cost, updated_at = v_now WHERE guild_id = p_guild_id AND user_id = p_user_id;
    IF v_item.stock != -1 THEN v_new_stock := v_item.stock - p_quantity; UPDATE shop_items SET stock = v_new_stock, updated_at = v_now WHERE guild_id = p_guild_id AND item_id = p_item_id; ELSE v_new_stock := -1; END IF;
    INSERT INTO inventory (guild_id, user_id, item_id, quantity) VALUES (p_guild_id, p_user_id, p_item_id, p_quantity)
    ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET quantity = inventory.quantity + p_quantity, updated_at = v_now;
    SELECT quantity INTO v_new_inv FROM inventory WHERE guild_id = p_guild_id AND user_id = p_user_id AND item_id = p_item_id;
    INSERT INTO transactions (transaction_id, guild_id, user_id, amount, balance_before, balance_after, transaction_type, description, metadata, "timestamp")
    VALUES (v_txn_id, p_guild_id, p_user_id, -v_total_cost, v_user_balance, v_new_balance, 'shop_purchase', 'Purchased ' || p_quantity || 'x ' || v_item.name, jsonb_build_object('item_id', p_item_id, 'quantity', p_quantity), v_now);
    RETURN QUERY SELECT true, NULL::TEXT, v_new_balance, v_new_stock, v_new_inv, v_total_cost, v_txn_id, v_item.name, v_item.emoji, v_item.price;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: enter_raffle_giveaway (Robust version with ticket limits and locking)
DROP FUNCTION IF EXISTS enter_raffle_giveaway(UUID, TEXT, TEXT, INTEGER, INTEGER);
DROP FUNCTION IF EXISTS enter_raffle_giveaway(UUID, TEXT, TEXT, INTEGER, INTEGER, INTEGER);
CREATE OR REPLACE FUNCTION enter_raffle_giveaway(
    p_giveaway_id UUID,
    p_guild_id TEXT,
    p_user_id TEXT,
    p_tickets INTEGER,
    p_raffle_cost INTEGER,
    p_max_tickets INTEGER DEFAULT 10
) RETURNS JSONB AS $$
DECLARE
    v_user_balance NUMERIC;
    v_total_cost NUMERIC;
    v_current_tickets INTEGER;
    v_new_tickets INTEGER;
    v_res RECORD;
    v_now TIMESTAMPTZ := NOW();
BEGIN
    -- 1. Lock the user's currency row
    SELECT balance INTO v_user_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO users (guild_id, user_id, balance, total_earned, total_spent, is_active)
        VALUES (p_guild_id, p_user_id, 0, 0, 0, true);
        v_user_balance := 0;
    END IF;

    -- Calculate total cost
    v_total_cost := p_tickets * p_raffle_cost;

    -- 2. Verify funds
    IF v_user_balance < v_total_cost THEN
        RETURN jsonb_build_object('success', false, 'error', 'Insufficient balance');
    END IF;

    -- 3. Lock user's existing giveaway entry
    SELECT tickets INTO v_current_tickets FROM giveaway_entries WHERE giveaway_id = p_giveaway_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN v_current_tickets := 0; END IF;

    v_new_tickets := v_current_tickets + p_tickets;

    -- 4. Verify max tickets rule
    IF v_new_tickets > p_max_tickets THEN
        RETURN jsonb_build_object('success', false, 'error', 'Exceeds maximum allowed tickets (' || p_max_tickets || ')');
    END IF;

    -- 5. Delegate to balance change for atomicity and transaction logging
    SELECT * INTO v_res FROM process_balance_change(p_guild_id, p_user_id, -v_total_cost, 'giveaway_entry', 'Raffle entry for giveaway ' || p_giveaway_id, jsonb_build_object('giveaway_id', p_giveaway_id, 'tickets', p_tickets));

    -- 6. Upsert the giveaway entry
    INSERT INTO giveaway_entries (giveaway_id, guild_id, user_id, tickets, amount_spent, entered_at)
    VALUES (p_giveaway_id, p_guild_id, p_user_id, p_tickets, v_total_cost, v_now)
    ON CONFLICT (giveaway_id, user_id) DO UPDATE SET 
        tickets = giveaway_entries.tickets + p_tickets, 
        amount_spent = giveaway_entries.amount_spent + v_total_cost,
        entered_at = v_now;

    -- 7. Update giveaway counter
    UPDATE giveaways SET total_entries = total_entries + p_tickets WHERE id = p_giveaway_id;

    RETURN jsonb_build_object('success', true, 'new_balance', v_res.new_balance, 'tickets_added', p_tickets, 'total_tickets', v_new_tickets);
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
GRANT EXECUTE ON FUNCTION process_balance_change TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION process_transfer TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION claim_daily_reward TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION claim_monthly_boost_reward TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION process_purchase TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION enter_raffle_giveaway TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION upsert_discord_user TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION sync_discord_user_guilds TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION expire_overdue_tasks TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION increment_giveaway_entries TO anon, authenticated, service_role;

-- Row Level Security
ALTER TABLE guilds ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE shop_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE archived_shop_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE moderation_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE strikes ENABLE ROW LEVEL SECURITY;
ALTER TABLE giveaways ENABLE ROW LEVEL SECURITY;
ALTER TABLE giveaway_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE web_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ad_views ENABLE ROW LEVEL SECURITY;
ALTER TABLE custom_ads ENABLE ROW LEVEL SECURITY;
ALTER TABLE ad_clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE global_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE global_task_claims ENABLE ROW LEVEL SECURITY;

-- Allow all for now (managed by service role)
DROP POLICY IF EXISTS "Public Full Access" ON guilds;
CREATE POLICY "Public Full Access" ON guilds FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON users;
CREATE POLICY "Public Full Access" ON users FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON shop_items;
CREATE POLICY "Public Full Access" ON shop_items FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON archived_shop_items;
CREATE POLICY "Public Full Access" ON archived_shop_items FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON giveaways;
CREATE POLICY "Public Full Access" ON giveaways FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON web_sessions;
CREATE POLICY "Public Full Access" ON web_sessions FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON ad_views;
CREATE POLICY "Public Full Access" ON ad_views FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON custom_ads;
CREATE POLICY "Public Full Access" ON custom_ads FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON ad_clients;
CREATE POLICY "Public Full Access" ON ad_clients FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON global_tasks;
CREATE POLICY "Public Full Access" ON global_tasks FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON global_task_claims;
CREATE POLICY "Public Full Access" ON global_task_claims FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON moderation_actions;
CREATE POLICY "Public Full Access" ON moderation_actions FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON strikes;
CREATE POLICY "Public Full Access" ON strikes FOR ALL USING (true);

-- Comments
COMMENT ON TABLE guilds IS 'Core Discord server configuration';
COMMENT ON TABLE users IS 'Economy and user state';
COMMENT ON TABLE web_sessions IS 'CMS authentication sessions with TTL and re-validation hardening';
COMMENT ON TABLE moderation_actions IS 'Persistent audit log for all manual and automated moderation';
COMMENT ON TABLE strikes IS 'Discord user strikes and warnings tracking';
COMMENT ON TABLE giveaways IS 'Server giveaway state with streak-aware winner tracking';
COMMENT ON TABLE ad_views IS 'Ad session tracking and verification';
COMMENT ON TABLE custom_ads IS 'Custom advertisements for blog posts and tools';
COMMENT ON TABLE ad_clients IS 'Registered clients for the ad system';
COMMENT ON TABLE global_tasks IS 'Configuration for global tasks like ad claiming';
COMMENT ON TABLE archived_shop_items IS 'Soft-archive for deleted items to allow legacy redemption';
COMMENT ON COLUMN web_sessions.max_expires_at IS 'Hard expiry timestamp regardless of activity (sliding window stops here)';
COMMENT ON COLUMN web_sessions.last_active_at IS 'Timestamp of the last request using this session';
COMMENT ON COLUMN web_sessions.last_permission_check IS 'Timestamp of the last Discord permission re-validation';

-- ADDITIONAL INDEXES
CREATE INDEX IF NOT EXISTS idx_web_sessions_max_expires ON web_sessions(max_expires_at);
CREATE INDEX IF NOT EXISTS idx_giveaways_lifecycle ON giveaways (guild_id, status);
CREATE INDEX IF NOT EXISTS idx_giveaways_embed ON giveaways (guild_id, channel_id, message_id);
CREATE INDEX IF NOT EXISTS idx_giveaways_scheduler ON giveaways (ends_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_giveaway_entries_fetch ON giveaway_entries (giveaway_id);

-- ADDITIONAL TRIGGERS
DROP TRIGGER IF EXISTS update_giveaways_updated_at ON giveaways;
CREATE TRIGGER update_giveaways_updated_at BEFORE UPDATE ON giveaways FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ROW LEVEL SECURITY (RLS) - COMPLETION
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE vote_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE discord_oauth_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE server_boosts ENABLE ROW LEVEL SECURITY;
ALTER TABLE announcements ENABLE ROW LEVEL SECURITY;
ALTER TABLE embeds ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_schedules ENABLE ROW LEVEL SECURITY;

-- POLICIES (Consolidated "Public Full Access" managed by service role)
DROP POLICY IF EXISTS "Public Full Access" ON admin_users;
CREATE POLICY "Public Full Access" ON admin_users FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON daily_claims;
CREATE POLICY "Public Full Access" ON daily_claims FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON inventory;
CREATE POLICY "Public Full Access" ON inventory FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON transactions;
CREATE POLICY "Public Full Access" ON transactions FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON tasks;
CREATE POLICY "Public Full Access" ON tasks FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON user_tasks;
CREATE POLICY "Public Full Access" ON user_tasks FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON task_settings;
CREATE POLICY "Public Full Access" ON task_settings FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON vote_logs;
CREATE POLICY "Public Full Access" ON vote_logs FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON giveaway_entries;
CREATE POLICY "Public Full Access" ON giveaway_entries FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON discord_oauth_logs;
CREATE POLICY "Public Full Access" ON discord_oauth_logs FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON server_boosts;
CREATE POLICY "Public Full Access" ON server_boosts FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON announcements;
CREATE POLICY "Public Full Access" ON announcements FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON embeds;
CREATE POLICY "Public Full Access" ON embeds FOR ALL USING (true);
DROP POLICY IF EXISTS "Public Full Access" ON channel_schedules;
CREATE POLICY "Public Full Access" ON channel_schedules FOR ALL USING (true);

