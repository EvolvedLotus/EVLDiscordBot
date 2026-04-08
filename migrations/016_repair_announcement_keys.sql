-- Repair script to ensure announcement_id is a valid target for upsert operations
-- This fixes the '42P10: no unique or exclusion constraint' error

DO $$ 
BEGIN
    -- Check if announcement_id is already a primary key
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'announcements' AND constraint_type = 'PRIMARY KEY'
    ) THEN
        ALTER TABLE announcements ADD PRIMARY KEY (announcement_id);
    END IF;

    -- Also ensure we have a unique constraint if for some reason the PK isn't enough
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'announcements' AND indexname = 'announcements_pkey'
    ) THEN
        CREATE UNIQUE INDEX IF NOT EXISTS announcements_id_unique_idx ON announcements (announcement_id);
    END IF;
END $$;
