-- Migration for Ad Claim hardening: session expiry and security flags

-- 1. Add columns to ad_views
ALTER TABLE ad_views 
ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP WITH TIME ZONE;

-- 2. Update existing entries to have an expiry if not set (15 mins from created_at)
UPDATE ad_views 
SET expires_at = created_at + INTERVAL '15 minutes' 
WHERE expires_at IS NULL;

-- 3. Add an index for cleanup
CREATE INDEX IF NOT EXISTS idx_ad_views_expires ON ad_views(expires_at);

-- 4. Comment for documentation
COMMENT ON COLUMN ad_views.expires_at IS 'Timestamp after which the ad session is no longer valid for verification';
COMMENT ON COLUMN ad_views.verified_at IS 'Timestamp when the ad was successfully verified and rewarded';
