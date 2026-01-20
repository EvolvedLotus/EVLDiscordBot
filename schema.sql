i COMMENT ON COLUMN guilds.boost_reward_enabled IS 'Whether boost rewards are enabled for this guild';
COMMENT ON COLUMN guilds.boost_reward_amount IS 'Amount of coins to reward per boost';
COMMENT ON COLUMN guilds.boost_log_channel_id IS 'Channel to log boost events';

-- =====================================================
-- USAGE INSTRUCTIONS
-- =====================================================
-- 
-- To check for balance discrepancies:
--   SELECT * FROM recalculate_user_balances();
--
-- To sync all user balances:
--   SELECT * FROM sync_all_user_balances();
--
-- To sync a specific user:
--   SELECT * FROM sync_user_balance('USER_ID', 'GUILD_ID');
--
-- To validate overall integrity:
--   SELECT * FROM validate_balance_integrity();
--
-- To view ad statistics:
--   SELECT user_id, COUNT(*) as total_views, SUM(CASE WHEN is_verified THEN 1 ELSE 0 END) as verified_views
--   FROM ad_views GROUP BY user_id ORDER BY total_views DESC;
--
-- =====================================================
