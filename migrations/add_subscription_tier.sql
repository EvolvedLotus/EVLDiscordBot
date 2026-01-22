ALTER TABLE guilds ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'free';
