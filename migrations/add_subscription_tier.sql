-- Add subscription_tier column to guilds table
ALTER TABLE guilds 
ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'free';

-- Add subscription_expiry column (optional, for future use)
ALTER TABLE guilds 
ADD COLUMN IF NOT EXISTS subscription_expiry TIMESTAMPTZ;

-- Comment for clarity
COMMENT ON COLUMN guilds.subscription_tier IS 'Subscription tier: free or premium';
