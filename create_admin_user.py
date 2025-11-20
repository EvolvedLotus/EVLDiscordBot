
import os
import hashlib
import getpass
from dotenv import load_dotenv
from supabase import create_client

def create_admin():
    print("=== Create Admin User ===")
    
    # Load env vars
    load_dotenv()
    
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not url or not key:
        print("⚠️  Supabase credentials not found in .env")
        url = input("Enter Supabase URL: ").strip()
        key = input("Enter Supabase Service Role Key: ").strip()
    
    if not url or not key:
        print("❌ Missing credentials. Exiting.")
        return

    try:
        supabase = create_client(url, key)
        
        username = input("Enter new admin username: ").strip()
        password = getpass.getpass("Enter new admin password: ").strip()
        confirm = getpass.getpass("Confirm password: ").strip()
        
        if password != confirm:
            print("❌ Passwords do not match!")
            return
            
        if not username or not password:
            print("❌ Username and password cannot be empty!")
            return
            
        # Hash password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        # Check if user exists
        print(f"Checking if user '{username}' exists...")
        result = supabase.table('admin_users').select('*').eq('username', username).execute()
        
        if result.data:
            print(f"⚠️  User '{username}' already exists.")
            update = input("Do you want to update the password? (y/n): ").lower()
            if update == 'y':
                supabase.table('admin_users').update({
                    'password_hash': hashed_password,
                    'is_active': True
                }).eq('username', username).execute()
                print("✅ Password updated successfully!")
            else:
                print("Operation cancelled.")
        else:
            # Create user
            user_data = {
                'username': username,
                'password_hash': hashed_password,
                'is_active': True,
                'is_superadmin': True
            }
            
            supabase.table('admin_users').insert(user_data).execute()
            print(f"✅ Admin user '{username}' created successfully!")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure the 'admin_users' table exists in your database.")
        print("You can create it by running the SQL in schema.sql")

if __name__ == "__main__":
    create_admin()
