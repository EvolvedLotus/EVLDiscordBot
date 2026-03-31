-- Migration to add atomic monthly boost reward claim and streak safety

CREATE OR REPLACE FUNCTION claim_monthly_boost_reward(
    p_guild_id TEXT,
    p_user_id TEXT,
    p_amount NUMERIC
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_updated_count INT;
    v_res RECORD;
BEGIN
    -- 1. Atomic update with condition to prevent double-rewards
    -- Only update if the user hasn't been rewarded in the last 30 days
    -- AND is currently considered active (or in grace period where we still track them)
    UPDATE server_boosts
    SET last_reward_at = NOW(),
        updated_at = NOW()
    WHERE guild_id = p_guild_id 
      AND user_id = p_user_id 
      AND is_active = True 
      AND (unboosted_at IS NULL) -- Do NOT reward while boost is actually lapsed (even in grace period)
      AND (last_reward_at IS NULL OR last_reward_at < NOW() - INTERVAL '30 days');

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;

    IF v_updated_count = 0 THEN
        RETURN jsonb_build_object('success', false, 'error', 'Not due for reward, boost lapsed, or inactive');
    END IF;

    -- 2. Award the coins using our existing atomic currency RPC
    SELECT * INTO v_res FROM process_balance_change(
        p_guild_id, 
        p_user_id, 
        p_amount, 
        'boost_reward', 
        'Monthly server boost reward'
    );

    RETURN jsonb_build_object(
        'success', true, 
        'new_balance', v_res.new_balance, 
        'transaction_id', v_res.transaction_id,
        'balance_before', v_res.balance_before,
        'balance_after', v_res.balance_after
    );
END;
$$;

-- Grant permission
GRANT EXECUTE ON FUNCTION claim_monthly_boost_reward TO anon;
GRANT EXECUTE ON FUNCTION claim_monthly_boost_reward TO authenticated;
GRANT EXECUTE ON FUNCTION claim_monthly_boost_reward TO service_role;
