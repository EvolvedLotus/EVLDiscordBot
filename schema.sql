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
