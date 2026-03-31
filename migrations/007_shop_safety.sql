-- =====================================================
-- MIGRATION 007: Shop & Inventory Safety Hardening
-- Fixes: atomic purchases, archived item redemption, price validation
-- =====================================================

-- 1. ATOMIC PURCHASE RPC: balance deduction + inventory increment + stock decrement
--    in a single Postgres transaction with row-level locking.
--    Replaces the threading.Lock approach which doesn't protect across multiple
--    bot processes or survive a restart mid-purchase.
CREATE OR REPLACE FUNCTION process_purchase(
    p_guild_id      TEXT,
    p_user_id       TEXT,
    p_item_id       TEXT,
    p_quantity       INTEGER,
    p_expected_price NUMERIC DEFAULT NULL  -- Price the user saw; NULL = skip validation
) RETURNS TABLE (
    success          BOOLEAN,
    error_message    TEXT,
    new_balance      NUMERIC,
    new_stock        INTEGER,
    inventory_total  INTEGER,
    total_cost       NUMERIC,
    transaction_id   UUID,
    item_name        TEXT,
    item_emoji       TEXT,
    actual_price     NUMERIC
) AS $$
DECLARE
    v_item           RECORD;
    v_user_balance   NUMERIC;
    v_total_cost     NUMERIC;
    v_new_balance    NUMERIC;
    v_new_stock      INTEGER;
    v_current_inv    INTEGER;
    v_new_inv        INTEGER;
    v_txn_id         UUID;
    v_now            TIMESTAMPTZ := NOW();
BEGIN
    -- 1. Lock and fetch the item row
    SELECT si.name, si.price, si.stock, si.is_active, si.emoji
    INTO v_item
    FROM shop_items si
    WHERE si.guild_id = p_guild_id AND si.item_id = p_item_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false, 'Item not found'::TEXT, 0::NUMERIC, 0::INTEGER,
            0::INTEGER, 0::NUMERIC, NULL::UUID, ''::TEXT, ''::TEXT, 0::NUMERIC;
        RETURN;
    END IF;

    IF NOT v_item.is_active THEN
        RETURN QUERY SELECT false, 'Item is not available for purchase'::TEXT, 0::NUMERIC, 0::INTEGER,
            0::INTEGER, 0::NUMERIC, NULL::UUID, ''::TEXT, ''::TEXT, 0::NUMERIC;
        RETURN;
    END IF;

    -- 2. Price-at-time-of-purchase validation
    IF p_expected_price IS NOT NULL AND p_expected_price != v_item.price THEN
        RETURN QUERY SELECT false,
            format('Price changed since you viewed it (was %s, now %s). Please try again.', p_expected_price, v_item.price)::TEXT,
            0::NUMERIC, 0::INTEGER, 0::INTEGER, 0::NUMERIC, NULL::UUID,
            v_item.name, COALESCE(v_item.emoji, '🛍️'), v_item.price;
        RETURN;
    END IF;

    -- 3. Stock check
    IF v_item.stock != -1 AND v_item.stock < p_quantity THEN
        RETURN QUERY SELECT false,
            format('Insufficient stock. Available: %s', v_item.stock)::TEXT,
            0::NUMERIC, v_item.stock, 0::INTEGER, 0::NUMERIC, NULL::UUID,
            v_item.name, COALESCE(v_item.emoji, '🛍️'), v_item.price;
        RETURN;
    END IF;

    v_total_cost := v_item.price * p_quantity;

    -- 4. Lock and fetch user balance
    SELECT balance INTO v_user_balance
    FROM users
    WHERE guild_id = p_guild_id AND user_id = p_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        -- Auto-create user
        INSERT INTO users (guild_id, user_id, balance, total_earned, total_spent, is_active)
        VALUES (p_guild_id, p_user_id, 0, 0, 0, true);
        v_user_balance := 0;
    END IF;

    -- 5. Balance check
    v_new_balance := v_user_balance - v_total_cost;
    IF v_new_balance < 0 THEN
        RETURN QUERY SELECT false,
            format('Insufficient balance. Need %s, have %s', v_total_cost, v_user_balance)::TEXT,
            v_user_balance, 0::INTEGER, 0::INTEGER, v_total_cost, NULL::UUID,
            v_item.name, COALESCE(v_item.emoji, '🛍️'), v_item.price;
        RETURN;
    END IF;

    -- === ALL VALIDATIONS PASSED — ATOMIC WRITES BEGIN ===

    v_txn_id := uuid_generate_v4();

    -- A. Deduct balance
    UPDATE users SET
        balance = v_new_balance,
        total_spent = total_spent + v_total_cost,
        updated_at = v_now
    WHERE guild_id = p_guild_id AND user_id = p_user_id;

    -- B. Decrement stock (if not unlimited)
    IF v_item.stock != -1 THEN
        v_new_stock := v_item.stock - p_quantity;
        UPDATE shop_items SET stock = v_new_stock, updated_at = v_now
        WHERE guild_id = p_guild_id AND item_id = p_item_id;
    ELSE
        v_new_stock := -1;
    END IF;

    -- C. Increment inventory (upsert)
    INSERT INTO inventory (guild_id, user_id, item_id, quantity, updated_at)
    VALUES (p_guild_id, p_user_id, p_item_id, p_quantity, v_now)
    ON CONFLICT (guild_id, user_id, item_id) DO UPDATE
    SET quantity = inventory.quantity + p_quantity, updated_at = v_now;

    -- Get new inventory total
    SELECT quantity INTO v_new_inv FROM inventory
    WHERE guild_id = p_guild_id AND user_id = p_user_id AND item_id = p_item_id;

    -- D. Log transaction
    INSERT INTO transactions (transaction_id, guild_id, user_id, amount, balance_before, balance_after,
        transaction_type, description, metadata, "timestamp")
    VALUES (v_txn_id, p_guild_id, p_user_id, -v_total_cost, v_user_balance, v_new_balance,
        'shop_purchase',
        format('Purchased %sx %s', p_quantity, v_item.name),
        jsonb_build_object('item_id', p_item_id, 'quantity', p_quantity,
            'item_name', v_item.name, 'unit_price', v_item.price),
        v_now);

    RETURN QUERY SELECT true, NULL::TEXT, v_new_balance, v_new_stock,
        COALESCE(v_new_inv, p_quantity), v_total_cost, v_txn_id,
        v_item.name, COALESCE(v_item.emoji, '🛍️'), v_item.price;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION process_purchase IS 'Atomic shop purchase: validates price/stock/balance, then deducts balance, decrements stock, increments inventory, and logs transaction in one Postgres transaction.';

-- 2. ARCHIVED SHOP ITEMS TABLE (if not exists from in-memory archive)
--    When items are deleted, they get soft-archived here so redemption
--    can still look up item definitions for items users already own.
CREATE TABLE IF NOT EXISTS archived_shop_items (
    guild_id    TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    price       NUMERIC NOT NULL,
    category    TEXT DEFAULT 'general',
    emoji       TEXT DEFAULT '🛍️',
    role_id     TEXT,
    duration_minutes INTEGER,
    metadata    JSONB DEFAULT '{}'::jsonb,
    archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    archived_by TEXT,

    PRIMARY KEY (guild_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_archived_shop_items_guild ON archived_shop_items(guild_id);

ALTER TABLE archived_shop_items ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access archived_shop_items" ON archived_shop_items;
CREATE POLICY "Service role full access archived_shop_items" ON archived_shop_items FOR ALL USING (true);

COMMENT ON TABLE archived_shop_items IS 'Soft-archive for deleted shop items. Allows redemption of items users already own after item is removed from store.';

-- Grant execute
GRANT EXECUTE ON FUNCTION process_purchase TO anon;
