-- Migration to allow -1 for infinite duration in tasks
-- This removes the existing check constraint and adds a new one that allows -1

-- Drop the existing constraint
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_duration_hours_check;

-- Add new constraint that allows positive numbers OR -1 for infinite duration
ALTER TABLE tasks ADD CONSTRAINT tasks_duration_hours_check 
  CHECK (duration_hours > 0 OR duration_hours = -1);
