-- Migration to address raffle race conditions natively in the database

CREATE OR REPLACE FUNCTION enter_raffle_giveaway(
    p_giveaway_id UUID,
    p_guild_id TEXT,
    p_user_id TEXT,
    p_tickets INT,
    p_raffle_cost INT,
    p_max_tickets INT,
    p_reason TEXT,
    p_transaction_type TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_balance INT;
    v_total_cost INT;
    v_current_tickets INT;
    v_new_tickets INT;
    v_existing_amount_spent INT;
    v_entry_record JSONB;
BEGIN
    -- 1. Lock the user's currency balance row for atomic update
    SELECT balance INTO v_current_balance 
    FROM user_profiles 
    WHERE guild_id = p_guild_id AND user_id = p_user_id 
    FOR UPDATE;

    IF NOT FOUND THEN
        -- Auto-create profile with 0 balance if it doesn't exist
        INSERT INTO user_profiles (guild_id, user_id, balance) 
        VALUES (p_guild_id, p_user_id, 0);
        v_current_balance := 0;
    END IF;

    -- Calculate total cost
    v_total_cost := p_tickets * p_raffle_cost;

    -- 2. Verify sufficient funds
    IF v_current_balance < v_total_cost THEN
        RETURN jsonb_build_object('success', false, 'error', 'Insufficient funds');
    END IF;

    -- 3. Lock user's existing giveaway entry if it exists to strictly respect max_tickets
    SELECT tickets, amount_spent INTO v_current_tickets, v_existing_amount_spent
    FROM giveaway_entries
    WHERE giveaway_id = p_giveaway_id AND user_id = p_user_id
    FOR UPDATE;

    IF NOT FOUND THEN
        v_current_tickets := 0;
        v_existing_amount_spent := 0;
    END IF;

    v_new_tickets := v_current_tickets + p_tickets;

    -- 4. Verify max tickets rule
    IF v_new_tickets > p_max_tickets THEN
        RETURN jsonb_build_object('success', false, 'error', 'Exceeds maximum allowed tickets');
    END IF;

    -- 5. Debit the user's balance
    UPDATE user_profiles
    SET balance = balance - v_total_cost
    WHERE guild_id = p_guild_id AND user_id = p_user_id;

    -- 6. Insert transaction audit log
    INSERT INTO currency_transactions (guild_id, user_id, amount, transaction_type, reason)
    VALUES (p_guild_id, p_user_id, -v_total_cost, p_transaction_type, p_reason);

    -- 7. Upsert the giveaway entry
    INSERT INTO giveaway_entries (giveaway_id, guild_id, user_id, tickets, amount_spent)
    VALUES (p_giveaway_id, p_guild_id, p_user_id, p_tickets, v_total_cost)
    ON CONFLICT (giveaway_id, user_id) 
    DO UPDATE SET 
        tickets = giveaway_entries.tickets + p_tickets,
        amount_spent = giveaway_entries.amount_spent + v_total_cost;

    -- 8. Increment denormalized overall giveaway total entries counter
    -- (We rely on increment_giveaway_entries or do it right here inline via lock)
    UPDATE giveaways 
    SET total_entries = total_entries + p_tickets
    WHERE id = p_giveaway_id;

    -- Return the upserted representation
    SELECT to_jsonb(ge) INTO v_entry_record 
    FROM giveaway_entries ge 
    WHERE giveaway_id = p_giveaway_id AND user_id = p_user_id;

    RETURN jsonb_build_object('success', true, 'entry', v_entry_record, 'new_balance', v_current_balance - v_total_cost);
END;
$$;
