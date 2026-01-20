import os
import discord
import asyncio
import logging
from core.data_manager import DataManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def force_sync_ad_tasks():
    dm = DataManager()
    
    # Initialize discord client just for this
    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)
    
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("No DISCORD_TOKEN found")
        return

    async with bot:
        @bot.event
        async def on_ready():
            logger.info(f"Logged in as {bot.user}")
            
            # 1. Fetch all guild message mappings for the ad task
            try:
                result = dm.admin_client.table('global_task_messages') \
                    .select('*') \
                    .eq('task_key', 'ad_claim_task') \
                    .execute()
                
                if not result.data:
                    logger.info("No global ad task messages found to update.")
                    await bot.close()
                    return

                logger.info(f"Found {len(result.data)} guilds with ad task messages.")

                for mapping in result.data:
                    guild_id = int(mapping['guild_id'])
                    channel_id = int(mapping['channel_id'])
                    message_id = int(mapping['message_id'])
                    
                    guild = bot.get_guild(guild_id)
                    if not guild:
                        logger.warning(f"Guild {guild_id} not found/cached. Skipping.")
                        continue
                        
                    channel = guild.get_channel(channel_id)
                    if not channel:
                        logger.warning(f"Channel {channel_id} not found in guild {guild_id}. Skipping.")
                        continue

                    try:
                        message = await channel.fetch_message(message_id)
                        
                        # Update the embed to look fresh
                        embed = message.embeds[0] if message.embeds else discord.Embed(title="🎁 Claim For 10 Free Points")
                        embed.title = "🎁 Claim For 10 Free Points (Ad Watching Task)"
                        embed.description = "Watch an ad to support us and earn **10 points** instantly! Now featuring evolved promotional content."
                        embed.color = discord.Color.purple()
                        embed.set_footer(text=f"Last Updated: {os.popen('date /t').read().strip()} {os.popen('time /t').read().strip()}")
                        
                        # Re-send/edit the message to ensure the NEW persistent view is registered
                        # Note: The 'GlobalTaskClaimView' is registered in bot.py, 
                        # so as long as the custom_id is 'claim_global_task', it will work.
                        await message.edit(embed=embed)
                        logger.info(f"✅ Updated ad task in guild {guild.name}")
                        
                    except discord.NotFound:
                        logger.warning(f"Message {message_id} not found in channel {channel_id}. It will be reposted by the monitor later.")
                    except Exception as e:
                        logger.error(f"Error updating message {message_id}: {e}")

                logger.info("Sync complete.")
            except Exception as e:
                logger.error(f"Sync failed: {e}")
            finally:
                await bot.close()

        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(force_sync_ad_tasks())
