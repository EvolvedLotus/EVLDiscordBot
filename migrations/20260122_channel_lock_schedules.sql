-- =====================================================
-- CHANNEL LOCK SCHEDULES TABLE (Premium Feature)
-- Run this on your Supabase instance
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
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
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
