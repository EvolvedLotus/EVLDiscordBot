
import os
import asyncio
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
if os.path.exists('.env.railway'):
    load_dotenv('.env.railway')
    logger.info("Loaded .env.railway")
elif os.path.exists('.env'):
    load_dotenv('.env')
    logger.info("Loaded .env")
else:
    logger.warning("No .env file found")

# Debug: Check if variables exist
keys = ['SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY']
for key in keys:
    val = os.getenv(key)
    if val:
        logger.info(f"Checking {key}: Present (Length: {len(val)})")
        if key == 'SUPABASE_URL':
            logger.info(f"URL host: {val.split('://')[-1].split('/')[0] if '://' in val else 'invalid'}")
    else:
        logger.error(f"Checking {key}: MISSING")

from core.data_manager import DataManager
from core.auth_manager import AuthManager

def create_admin():
    try:
        # Initialize managers
        data_manager = DataManager()
        # JWT secret is needed for AuthManager init but not for password hashing or DB insert of user
        auth_manager = AuthManager(data_manager, jwt_secret="temp_secret")

        username = "admin"
        password = "password123"
        
        # Check if user exists
        existing = data_manager.admin_client.table('admin_users').select('*').eq('username', username).execute()
        
        password_hash = auth_manager._hash_password(password)
        
        user_data = {
            'username': username,
            'password_hash': password_hash,
            'is_superadmin': True,
            'is_active': True,
            'created_at': 'now()',
            'updated_at': 'now()'
        }

        if existing.data:
            logger.info(f"Updating existing admin user '{username}'...")
            data_manager.admin_client.table('admin_users').update(user_data).eq('username', username).execute()
        else:
            logger.info(f"Creating new admin user '{username}'...")
            data_manager.admin_client.table('admin_users').insert(user_data).execute()

        logger.info(f"✅ Admin user '{username}' configured successfully.")
        logger.info(f"👉 Username: {username}")
        logger.info(f"👉 Password: {password}")

    except Exception as e:
        logger.error(f"❌ Failed to create admin user: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_admin()
