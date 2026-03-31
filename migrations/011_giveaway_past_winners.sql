-- Migration to add past_winners tracking for giveaway rerolls

ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS past_winners text[] DEFAULT '{}';
