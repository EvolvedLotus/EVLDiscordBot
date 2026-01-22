import os
import asyncio
from dotenv import load_dotenv
from core.data_manager import DataManager

# Load environment variables
load_dotenv()

async def upgrade_server():
    print("🚀 Starting server upgrade script...")
    
    try:
        # Initialize DataManager
        dm = DataManager()
        
        # List all guilds to find EvolvedLotus
        print("🔍 Searching for 'EvolvedLotus' server...")
        
        # Note: DataManager uses synchronous supabase client internally but wrapped in async-like structure in some places?
        # Actually in _create_supabase_client it returns a client. 
        # The execute methods depend on the library version. 
        # Looking at core/data_manager.py, it calls .execute() directly.
        
        # Let's try to query directly using the admin_client
        response = dm.admin_client.table('guilds').select('*').execute()
        
        guilds = response.data
        target_guild = None
        
        for guild in guilds:
            print(f"  - Found guild: {guild.get('server_name')} ({guild.get('guild_id')}) - Tier: {guild.get('subscription_tier')}")
            if "evolvedlotus" in guild.get('server_name', '').lower().replace(" ", ""):
                target_guild = guild
                break
        
        if not target_guild:
            print("❌ 'EvolvedLotus' server not found in database!")
            return
            
        guild_id = target_guild['guild_id']
        current_tier = target_guild.get('subscription_tier', 'free')
        
        print(f"✅ Found target guild: {target_guild.get('server_name')} (ID: {guild_id})")
        print(f"Current Tier: {current_tier}")
        
        if current_tier == 'premium':
            print("✨ Server is already Premium!")
        else:
            print("🆙 Upgrading server to Premium...")
            dm.admin_client.table('guilds').update({'subscription_tier': 'premium'}).eq('guild_id', guild_id).execute()
            print("✅ Upgrade successful!")
            
            # Verify
            verify_response = dm.admin_client.table('guilds').select('subscription_tier').eq('guild_id', guild_id).execute()
            new_tier = verify_response.data[0]['subscription_tier']
            print(f"New Tier Status: {new_tier}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(upgrade_server())
