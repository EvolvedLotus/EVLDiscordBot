-- 004_giveaway_tables.sql - Giveaway System Schema
-- Includes winner tracking and cost-based entries

-- 1. GIVEAWAYS table
CREATE TABLE IF NOT EXISTS giveaways (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    guild_id text NOT NULL,
    created_by text NOT NULL,
    prize_source text NOT NULL,
    shop_item_id text,
    prize_name text NOT NULL,
    prize_description text,
    prize_image_url text,
    winner_count integer NOT NULL DEFAULT 1,
    entry_mode text NOT NULL,
    required_role_ids text[],
    raffle_cost integer,
    raffle_max_tickets_per_user integer DEFAULT 10,
    tag_role_id text,
    custom_message text,
    channel_id text NOT NULL,
    message_id text,
    status text NOT NULL DEFAULT 'active',
    start_at timestamptz,
    ends_at timestamptz NOT NULL,
    ended_at timestamptz,
    winner_user_ids text[] DEFAULT '{}',
    past_winners text[] DEFAULT '{}', -- Track winners from previous draws for this ID
    total_entries integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- 2. GIVEAWAY ENTRIES table
CREATE TABLE IF NOT EXISTS giveaway_entries (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    giveaway_id uuid NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
    guild_id text NOT NULL,
    user_id text NOT NULL,
    tickets integer NOT NULL DEFAULT 1,
    amount_spent integer NOT NULL DEFAULT 0,
    entered_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(giveaway_id, user_id)
);

-- 3. INDEXES
CREATE INDEX IF NOT EXISTS idx_giveaways_lifecycle ON giveaways (guild_id, status);
CREATE INDEX IF NOT EXISTS idx_giveaways_embed ON giveaways (guild_id, channel_id, message_id);
CREATE INDEX IF NOT EXISTS idx_giveaways_scheduler ON giveaways (ends_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_giveaway_entries_fetch ON giveaway_entries (giveaway_id);

-- 4. TRIGGER for updated_at
CREATE OR REPLACE FUNCTION update_giveaway_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_giveaway_updated_at_trigger ON giveaways;
CREATE TRIGGER update_giveaway_updated_at_trigger
BEFORE UPDATE ON giveaways
FOR EACH ROW
EXECUTE FUNCTION update_giveaway_updated_at();

-- 5. ROW LEVEL SECURITY (RLS)
ALTER TABLE giveaways ENABLE ROW LEVEL SECURITY;
ALTER TABLE giveaway_entries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Enable read access for all users" ON giveaways;
CREATE POLICY "Enable read access for all users" ON giveaways FOR SELECT USING (true);

DROP POLICY IF EXISTS "Enable read access for all users" ON giveaway_entries;
CREATE POLICY "Enable read access for all users" ON giveaway_entries FOR SELECT USING (true);

DROP POLICY IF EXISTS "Enable all access for service role" ON giveaways;
CREATE POLICY "Enable all access for service role" ON giveaways USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Enable all access for service role" ON giveaway_entries;
CREATE POLICY "Enable all access for service role" ON giveaway_entries USING (true) WITH CHECK (true);

