-- Add status column to announcements table if it doesn't exist
ALTER TABLE IF EXISTS announcements 
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'published';

-- Also ensure we have a created_at column if it's missing (usually there but good safety)
ALTER TABLE IF EXISTS announcements 
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Add index for status filtering
CREATE INDEX IF NOT EXISTS idx_announcements_status ON announcements(status);

-- NOTE: If you are using Supabase, remember to click "Settings" -> "API" -> "Reload PostgREST Schema" 
-- or restart the service if the 'status' column is not detected immediately.
