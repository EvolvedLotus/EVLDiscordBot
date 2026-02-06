import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import json
import logging
from supabase import create_client, Client

# Configure logging
logger = logging.getLogger(__name__)

class PremiumSync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tools_db_url = os.getenv('TOOLS_SUPABASE_URL')
        self.tools_db_key = os.getenv('TOOLS_SUPABASE_KEY')
        self.tools_client: Client = None
        self.links_file = 'data/global/premium_links.json'
        
        if self.tools_db_url and self.tools_db_key:
            try:
                self.tools_client = create_client(self.tools_db_url, self.tools_db_key)
                logger.info("✅ Connected to Tools Database for Premium Sync")
            except Exception as e:
                logger.error(f"❌ Failed to connect to Tools Database: {e}")
        else:
            logger.warning("⚠️ TOOLS_SUPABASE_URL or TOOLS_SUPABASE_KEY not found. Premium sync will not work.")

        # Load links
        self.premium_links = self.load_links()

        # Start sync loop
        self.sync_premium_status.start()

    def load_links(self):
        """Load user-email links from JSON"""
        if os.path.exists(self.links_file):
            try:
                with open(self.links_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load premium links: {e}")
        return {}

    def save_links(self):
        """Save user-email links to JSON"""
        try:
            os.makedirs(os.path.dirname(self.links_file), exist_ok=True)
            with open(self.links_file, 'w') as f:
                json.dump(self.premium_links, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save premium links: {e}")

    def cog_unload(self):
        self.sync_premium_status.cancel()

    @app_commands.command(name="link_premium", description="Link your EvolvedLotus subscription to this Discord account")
    @app_commands.describe(email="The email address used for your purchase")
    async def link_premium(self, interaction: discord.Interaction, email: str):
        """Link a Discord account to a Premium Subscription via email"""
        if not self.tools_client:
            await interaction.response.send_message("❌ Premium system is currently unavailable (DB Connection Missing).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Check if email exists in premium_users table (Tools DB)
            # Normalizing email
            email_lower = email.lower().strip()
            
            response = self.tools_client.table('premium_users').select('*').eq('email', email_lower).execute()
            
            if not response.data or len(response.data) == 0:
                await interaction.followup.send(f"❌ No subscription found for `{email_lower}`. Please ensure you have purchased a Growth Insider plan.", ephemeral=True)
                return
            
            user_data = response.data[0]
            
            if not user_data.get('is_premium'):
                 await interaction.followup.send(f"⚠️ Subscription found for `{email_lower}`, but it is currently inactive.", ephemeral=True)
                 return

            if user_data.get('premium_tier') != 'growth_insider':
                await interaction.followup.send(f"found subscription for `{email_lower}` is '{user_data.get('premium_tier', 'free')}', but 'growth_insider' is required for Discord perks.", ephemeral=True)
                return

            # Link confirmed
            user_id = str(interaction.user.id)
            self.premium_links[user_id] = email_lower
            self.save_links()

            await interaction.followup.send(f"✅ **Success!** Your Discord account is now linked to `{email_lower}`.\nPremium perks will be synced to your servers shortly.", ephemeral=True)
            
            # Trigger immediate sync for this user
            await self._sync_user(interaction.user.id, email_lower)

        except Exception as e:
            logger.error(f"Link error: {e}")
            await interaction.followup.send("❌ An error occurred while linking your account. Please try again later.", ephemeral=True)

    @tasks.loop(minutes=5)
    async def sync_premium_status(self):
        """Background task to sync premium status for all linked users"""
        if not self.tools_client:
            return

        logger.info("🔄 Running Premium Sync...")
        
        # We iterate over our local links because querying the DB for all might be expensive or unrelated
        for user_id_str, email in self.premium_links.items():
            await self._sync_user(int(user_id_str), email)

    async def _sync_user(self, user_id: int, email: str):
        """Sync a single user's premium status to their guilds"""
        try:
            # 1. Get Status from Tools DB
            response = self.tools_client.table('premium_users').select('*').eq('email', email).execute()
            
            is_premium = False
            tier = 'free'
            
            if response.data and len(response.data) > 0:
                data = response.data[0]
                if data.get('is_premium') and data.get('premium_tier') == 'growth_insider':
                    is_premium = True
                    tier = 'premium'

            # 2. Find Guilds Owned by User
            # We need to query our LOCAL database (bot db) for guilds owned by this user
            # Assuming 'guilds' table has 'owner_id'
            
            # Using the main DataManager attached to the bot
            # Note: bot.data_manager is available if this cog is loaded after main init
            if not hasattr(self.bot, 'data_manager'):
                return

            # Helper to update guild tier locally
            # We can't easily query "all guilds owned by X" without a direct DB query or iterating cache
            # Iterating cache is faster for a bot
            
            user_guilds = [g for g in self.bot.guilds if g.owner_id == user_id]
            
            for guild in user_guilds:
                try:
                    current_tier = 'free'
                    # Check current DB state
                    res = self.bot.data_manager.supabase.table('guilds').select('subscription_tier').eq('guild_id', str(guild.id)).execute()
                    if res.data:
                        current_tier = res.data[0].get('subscription_tier', 'free')

                    if is_premium and current_tier != 'premium':
                        # Upgrade
                        self.bot.data_manager.supabase.table('guilds').update({'subscription_tier': 'premium'}).eq('guild_id', str(guild.id)).execute()
                        logger.info(f"💎 Upgraded guild {guild.name} (Owner: {user_id}) to Premium")
                        
                        # Optional: Send DM
                        try:
                            owner = guild.owner
                            if owner:
                                await owner.send(f"🌟 Your server **{guild.name}** has been upgraded to **Premium** via your Growth Insider subscription!")
                        except:
                            pass

                    elif not is_premium and current_tier == 'premium':
                        # Downgrade (expired)
                        self.bot.data_manager.supabase.table('guilds').update({'subscription_tier': 'free'}).eq('guild_id', str(guild.id)).execute()
                        logger.info(f"📉 Downgraded guild {guild.name} (Owner: {user_id}) to Free")
                except Exception as ex:
                    logger.error(f"Error syncing guild {guild.id}: {ex}")

        except Exception as e:
            logger.error(f"Error syncing user {user_id}: {e}")

    @sync_premium_status.before_loop
    async def before_sync_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(PremiumSync(bot))
