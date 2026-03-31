-- Migration for session hardening: max lifetime, idle timeout, and permission re-validation tracking

-- 1. Add columns to web_sessions
ALTER TABLE web_sessions 
ADD COLUMN IF NOT EXISTS max_expires_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS last_permission_check TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- 2. Update existing sessions to have a default max lifetime of 30 days if not set
UPDATE web_sessions 
SET max_expires_at = created_at + INTERVAL '30 days' 
WHERE max_expires_at IS NULL;

-- 3. Add an index for cleaner cleanup
CREATE INDEX IF NOT EXISTS idx_web_sessions_max_expires ON web_sessions(max_expires_at);

-- 4. Comment for documentation
COMMENT ON COLUMN web_sessions.max_expires_at IS 'Hard expiry timestamp regardless of activity (sliding window stops here)';
COMMENT ON COLUMN web_sessions.last_active_at IS 'Timestamp of the last request using this session';
COMMENT ON COLUMN web_sessions.last_permission_check IS 'Timestamp of the last Discord permission re-validation';
