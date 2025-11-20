#!/usr/bin/env python3
"""
Migration script to add bot_status_message and bot_status_type columns to guilds table.
"""
import os
import sys
from supabase import create_client, Client

def main():
    # Get environment variables
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')  # Use service role for schema changes

    if not url or not key:
        print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables")
        sys.exit(1)

    try:
        # Initialize Supabase client
        supabase = create_client(url, key)

        # Check if columns already exist
        result = supabase.table('guilds').select('bot_status_message, bot_status_type').limit(1).execute()

        # If no error occurred, columns likely exist
        print("✅ Bot status columns already exist")
        return

    except Exception as e:
        # Columns don't exist or other error
        try:
            # Try to add the columns
            print("🔄 Adding bot_status_message and bot_status_type columns...")

            # Use raw SQL to alter table
            # Note: In production, you'd want to use proper database migration tools
            from supabase.connection import Connection

            # Execute raw SQL
            sql = """
            ALTER TABLE guilds
            ADD COLUMN IF NOT EXISTS bot_status_message TEXT,
            ADD COLUMN IF NOT EXISTS bot_status_type TEXT DEFAULT 'watching';
            """

            # This will only work if the Supabase service role has permission to alter tables
            # For production, this should be done manually via the Supabase dashboard or migrations
            print("⚠️  Please run the following SQL in your Supabase SQL editor:")
            print()
            print("ALTER TABLE guilds")
            print("ADD COLUMN IF NOT EXISTS bot_status_message TEXT,")
            print("ADD COLUMN IF NOT EXISTS bot_status_type TEXT DEFAULT 'watching';")
            print()

        except Exception as alter_error:
            print(f"❌ Failed to alter table: {alter_error}")
            print("⚠️  You may need to manually add the columns via the Supabase dashboard")

if __name__ == "__main__":
    main()
