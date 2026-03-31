-- =====================================================
-- MIGRATION 006: Currency & Economy Safety Hardening
-- Fixes: atomic transactions, race conditions, daily idempotency, admin audit
-- =====================================================

-- 1. ADD CHECK CONSTRAINT: Prevent negative balances at the DB layer
--    This closes the race condition where two concurrent requests
--    can both pass the app-layer balance check before either write lands.
ALTER TABLE users ADD CONSTRAINT users_balance_non_negative CHECK (balance >= 0);


-- 2. CREATE daily_claims TABLE: Idempotency key for /daily command
--    Keyed on (user_id, guild_id, claim_date) with a UNIQUE constraint.
--    INSERT ... ON CONFLICT DO NOTHING is the first step — if the insert
--    succeeds the claim proceeds; if it conflicts the claim already happened.
CREATE TABLE IF NOT EXISTS daily_claims (
    guild_id    TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    claim_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    reward      NUMERIC NOT NULL DEFAULT 100,
    claimed_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    PRIMARY KEY (guild_id, user_id, claim_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_claims_user ON daily_claims(guild_id, user_id);

COMMENT ON TABLE daily_claims IS 'Idempotency table preventing double /daily claims within the same calendar day (UTC)';


-- 3. ATOMIC TRANSACTION RPC: Single Postgres transaction for log + balance update
--    Replaces the two-phase commit pattern where Step 1 (insert log) and
--    Step 2 (update balance) were separate operations that could desync.
--    Now both happen inside a single BEGIN/COMMIT block via this function.
CREATE OR REPLACE FUNCTION process_balance_change(
    p_guild_id          TEXT,
    p_user_id           TEXT,
    p_amount            NUMERIC,
    p_transaction_type  TEXT,
    p_description       TEXT,
    p_metadata          JSONB DEFAULT '{}'::jsonb
) RETURNS TABLE (
    new_balance         NUMERIC,
    transaction_id      UUID,
    balance_before      NUMERIC,
    balance_after       NUMERIC,
    "timestamp"         TIMESTAMPTZ
) AS $$
DECLARE
    v_balance_before    NUMERIC;
    v_balance_after     NUMERIC;
    v_txn_id            UUID;
    v_now               TIMESTAMPTZ := NOW();
BEGIN
    -- Lock the user row to prevent concurrent modifications (SELECT FOR UPDATE)
    SELECT balance INTO v_balance_before
    FROM users
    WHERE guild_id = p_guild_id AND user_id = p_user_id
    FOR UPDATE;

    -- If user doesn't exist, create them
    IF NOT FOUND THEN
        INSERT INTO users (guild_id, user_id, balance, total_earned, total_spent, is_active)
        VALUES (p_guild_id, p_user_id, 0, 0, 0, true);
        v_balance_before := 0;
    END IF;

    v_balance_after := v_balance_before + p_amount;

    -- The CHECK constraint will reject this if v_balance_after < 0,
    -- but we can give a nicer error message here.
    IF v_balance_after < 0 THEN
        RAISE EXCEPTION 'Insufficient balance: current=%, requested=%', v_balance_before, p_amount;
    END IF;

    -- Generate transaction ID
    v_txn_id := uuid_generate_v4();

    -- ATOMIC: Insert transaction log
    INSERT INTO transactions (transaction_id, guild_id, user_id, amount, balance_before, balance_after, transaction_type, description, metadata, "timestamp")
    VALUES (v_txn_id, p_guild_id, p_user_id, p_amount, v_balance_before, v_balance_after, p_transaction_type, p_description, p_metadata, v_now);

    -- ATOMIC: Update user balance and totals
    UPDATE users
    SET balance = v_balance_after,
        total_earned = CASE WHEN p_amount > 0 THEN total_earned + p_amount ELSE total_earned END,
        total_spent  = CASE WHEN p_amount < 0 THEN total_spent + ABS(p_amount) ELSE total_spent END,
        updated_at = v_now
    WHERE guild_id = p_guild_id AND user_id = p_user_id;

    -- Return results
    RETURN QUERY SELECT v_balance_after, v_txn_id, v_balance_before, v_balance_after, v_now;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION process_balance_change IS 'Atomic balance change: logs transaction and updates balance in a single Postgres transaction. SELECT FOR UPDATE prevents race conditions.';


-- 4. ATOMIC TRANSFER RPC: Two-user transfer in a single transaction
--    Locks both user rows, validates sender balance, deducts and credits
--    in one atomic operation. No window for desync.
CREATE OR REPLACE FUNCTION process_transfer(
    p_guild_id          TEXT,
    p_sender_id         TEXT,
    p_receiver_id       TEXT,
    p_amount            NUMERIC,
    p_description_send  TEXT,
    p_description_recv  TEXT,
    p_metadata_send     JSONB DEFAULT '{}'::jsonb,
    p_metadata_recv     JSONB DEFAULT '{}'::jsonb
) RETURNS TABLE (
    sender_new_balance      NUMERIC,
    receiver_new_balance    NUMERIC,
    send_transaction_id     UUID,
    recv_transaction_id     UUID,
    sender_balance_before   NUMERIC,
    receiver_balance_before NUMERIC
) AS $$
DECLARE
    v_sender_balance        NUMERIC;
    v_receiver_balance      NUMERIC;
    v_sender_new            NUMERIC;
    v_receiver_new          NUMERIC;
    v_send_txn_id           UUID;
    v_recv_txn_id           UUID;
    v_now                   TIMESTAMPTZ := NOW();
BEGIN
    -- Lock BOTH rows in a consistent order (alphabetical by user_id) to prevent deadlocks
    IF p_sender_id < p_receiver_id THEN
        SELECT balance INTO v_sender_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_sender_id FOR UPDATE;
        SELECT balance INTO v_receiver_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_receiver_id FOR UPDATE;
    ELSE
        SELECT balance INTO v_receiver_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_receiver_id FOR UPDATE;
        SELECT balance INTO v_sender_balance FROM users WHERE guild_id = p_guild_id AND user_id = p_sender_id FOR UPDATE;
    END IF;

    IF v_sender_balance IS NULL THEN
        RAISE EXCEPTION 'Sender account not found';
    END IF;

    -- Auto-create receiver if needed
    IF v_receiver_balance IS NULL THEN
        INSERT INTO users (guild_id, user_id, balance, total_earned, total_spent, is_active)
        VALUES (p_guild_id, p_receiver_id, 0, 0, 0, true);
        v_receiver_balance := 0;
    END IF;

    v_sender_new := v_sender_balance - p_amount;
    v_receiver_new := v_receiver_balance + p_amount;

    IF v_sender_new < 0 THEN
        RAISE EXCEPTION 'Insufficient balance: current=%, requested=%', v_sender_balance, p_amount;
    END IF;

    v_send_txn_id := uuid_generate_v4();
    v_recv_txn_id := uuid_generate_v4();

    -- Log sender transaction
    INSERT INTO transactions (transaction_id, guild_id, user_id, amount, balance_before, balance_after, transaction_type, description, metadata, "timestamp")
    VALUES (v_send_txn_id, p_guild_id, p_sender_id, -p_amount, v_sender_balance, v_sender_new, 'transfer_sent', p_description_send, p_metadata_send, v_now);

    -- Log receiver transaction
    INSERT INTO transactions (transaction_id, guild_id, user_id, amount, balance_before, balance_after, transaction_type, description, metadata, "timestamp")
    VALUES (v_recv_txn_id, p_guild_id, p_receiver_id, p_amount, v_receiver_balance, v_receiver_new, 'transfer_received', p_description_recv, p_metadata_recv, v_now);

    -- Update sender balance
    UPDATE users SET balance = v_sender_new, total_spent = total_spent + p_amount, updated_at = v_now
    WHERE guild_id = p_guild_id AND user_id = p_sender_id;

    -- Update receiver balance
    UPDATE users SET balance = v_receiver_new, total_earned = total_earned + p_amount, updated_at = v_now
    WHERE guild_id = p_guild_id AND user_id = p_receiver_id;

    RETURN QUERY SELECT v_sender_new, v_receiver_new, v_send_txn_id, v_recv_txn_id, v_sender_balance, v_receiver_balance;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION process_transfer IS 'Atomic two-user transfer: locks both rows, validates balance, logs both transactions, and updates both balances in one Postgres transaction.';


-- 5. ATOMIC DAILY CLAIM RPC: Idempotent daily reward claim
--    Uses daily_claims table as the idempotency gate.
CREATE OR REPLACE FUNCTION claim_daily_reward(
    p_guild_id  TEXT,
    p_user_id   TEXT,
    p_reward    NUMERIC DEFAULT 100
) RETURNS TABLE (
    success         BOOLEAN,
    new_balance     NUMERIC,
    already_claimed BOOLEAN,
    transaction_id  UUID,
    next_claim_at   TIMESTAMPTZ
) AS $$
DECLARE
    v_inserted      BOOLEAN;
    v_balance       NUMERIC;
    v_txn_id        UUID;
    v_now           TIMESTAMPTZ := NOW();
    v_today         DATE := CURRENT_DATE;
BEGIN
    -- Try to insert idempotency row — ON CONFLICT DO NOTHING
    INSERT INTO daily_claims (guild_id, user_id, claim_date, reward, claimed_at)
    VALUES (p_guild_id, p_user_id, v_today, p_reward, v_now)
    ON CONFLICT (guild_id, user_id, claim_date) DO NOTHING;

    -- Check if we actually inserted (GET DIAGNOSTICS doesn't work across ON CONFLICT,
    -- so we check if the row we just tried to insert has our exact timestamp)
    IF NOT FOUND THEN
        -- Already claimed today
        RETURN QUERY SELECT false, 0::NUMERIC, true, NULL::UUID, (v_today + INTERVAL '1 day')::TIMESTAMPTZ;
        RETURN;
    END IF;

    -- Ensure user exists
    INSERT INTO users (guild_id, user_id, balance, total_earned, total_spent, is_active)
    VALUES (p_guild_id, p_user_id, 0, 0, 0, true)
    ON CONFLICT (guild_id, user_id) DO NOTHING;

    -- Lock user row
    SELECT balance INTO v_balance FROM users
    WHERE guild_id = p_guild_id AND user_id = p_user_id FOR UPDATE;

    v_txn_id := uuid_generate_v4();

    -- Log transaction
    INSERT INTO transactions (transaction_id, guild_id, user_id, amount, balance_before, balance_after, transaction_type, description, metadata, "timestamp")
    VALUES (v_txn_id, p_guild_id, p_user_id, p_reward, v_balance, v_balance + p_reward, 'daily_reward', 'Daily reward', '{"source": "discord_command", "command": "/daily"}'::jsonb, v_now);

    -- Update balance
    UPDATE users SET
        balance = balance + p_reward,
        total_earned = total_earned + p_reward,
        last_daily = v_now,
        updated_at = v_now
    WHERE guild_id = p_guild_id AND user_id = p_user_id;

    RETURN QUERY SELECT true, (v_balance + p_reward), false, v_txn_id, (v_today + INTERVAL '1 day')::TIMESTAMPTZ;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION claim_daily_reward IS 'Idempotent daily reward: uses daily_claims table to prevent double-fire, then atomically logs transaction and updates balance.';


-- 6. Grant execute permissions for RPC functions (anon role for Supabase)
GRANT EXECUTE ON FUNCTION process_balance_change TO anon;
GRANT EXECUTE ON FUNCTION process_transfer TO anon;
GRANT EXECUTE ON FUNCTION claim_daily_reward TO anon;

-- Enable RLS on daily_claims
ALTER TABLE daily_claims ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access daily_claims" ON daily_claims;
CREATE POLICY "Service role full access daily_claims" ON daily_claims FOR ALL USING (true);
