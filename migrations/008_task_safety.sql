-- 008_task_safety.sql
-- Adds safe task expiration and submission limit policies

-- 1. Add submission attempts tracking to user_tasks table
ALTER TABLE user_tasks 
ADD COLUMN IF NOT EXISTS submission_attempts INTEGER DEFAULT 0;

-- 2. Add Postgres background RPC to expire tasks without impacting active reviews
CREATE OR REPLACE FUNCTION expire_overdue_tasks()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    expired_tasks_count INTEGER := 0;
    expired_user_tasks_count INTEGER := 0;
BEGIN
    -- Only expire user_tasks that have NOT reached the review queue. 
    -- If a user submitted their proof right before the deadline, preserve their submission.
    -- If they were just holding the claim (in_progress), expire it.
    WITH updated_user_tasks AS (
        UPDATE user_tasks
        SET status = 'expired', updated_at = NOW()
        WHERE status = 'in_progress' AND deadline < NOW()
        RETURNING id
    )
    SELECT count(*) INTO expired_user_tasks_count FROM updated_user_tasks;

    -- Expire parent tasks
    WITH updated_tasks AS (
        UPDATE tasks
        SET status = 'expired', updated_at = NOW()
        WHERE status = 'active' AND expires_at < NOW()
        RETURNING task_id
    )
    SELECT count(*) INTO expired_tasks_count FROM updated_tasks;

    RETURN expired_tasks_count + expired_user_tasks_count;
END;
$$;
