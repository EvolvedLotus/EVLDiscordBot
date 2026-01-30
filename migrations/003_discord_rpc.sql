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

-- ADMIN USERS (If not exists, though it's referenced)
-- NOTE: password_hash is nullable for Discord OAuth logins
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username TEXT UNIQUE,
    password_hash TEXT,  -- Can be NULL for Discord OAuth users
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

-- If the table already exists with NOT NULL, alter it:
ALTER TABLE admin_users ALTER COLUMN password_hash DROP NOT NULL;

-- RPC: upsert_discord_user
CREATE OR REPLACE FUNCTION upsert_discord_user(
    p_discord_id TEXT,
    p_discord_username TEXT,
    p_discord_avatar TEXT,
    p_access_token TEXT,
    p_refresh_token TEXT,
    p_token_expires_at TIMESTAMPTZ,
    p_owned_guild_ids TEXT[]
) RETURNS UUID AS $$
DECLARE
    v_user_id UUID;
BEGIN
    INSERT INTO admin_users (
        discord_id, discord_username, discord_avatar, 
        discord_access_token, discord_refresh_token, discord_token_expires_at, 
        allowed_guild_ids, username
    ) VALUES (
        p_discord_id, p_discord_username, p_discord_avatar,
        p_access_token, p_refresh_token, p_token_expires_at,
        p_owned_guild_ids, p_discord_username
    )
    ON CONFLICT (discord_id) DO UPDATE SET
        discord_username = EXCLUDED.discord_username,
        discord_avatar = EXCLUDED.discord_avatar,
        discord_access_token = EXCLUDED.discord_access_token,
        discord_refresh_token = EXCLUDED.discord_refresh_token,
        discord_token_expires_at = EXCLUDED.discord_token_expires_at,
        allowed_guild_ids = EXCLUDED.allowed_guild_ids,
        last_login = NOW(),
        updated_at = NOW()
    RETURNING id INTO v_user_id;
    
    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: sync_discord_user_guilds
CREATE OR REPLACE FUNCTION sync_discord_user_guilds(
    p_discord_id TEXT,
    p_owned_guild_ids TEXT[]
) RETURNS VOID AS $$
BEGIN
    UPDATE admin_users
    SET allowed_guild_ids = p_owned_guild_ids,
        updated_at = NOW()
    WHERE discord_id = p_discord_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
