CREATE OR REPLACE FUNCTION increment_giveaway_entries(g_id uuid, t_count integer)
RETURNS void AS $$
BEGIN
    UPDATE giveaways
    SET total_entries = total_entries + t_count
    WHERE id = g_id;
END;
$$ LANGUAGE plpgsql;
