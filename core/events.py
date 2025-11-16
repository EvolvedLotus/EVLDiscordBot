"""
Global event handlers for the Discord bot
"""

import discord
from discord.ext import commands
from . import data_manager
import logging

logger = logging.getLogger(__name__)

class EventHandler:
    """Handles global bot events"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.setup_events()

    def setup_events(self):
        """Register all event handlers"""

        @self.bot.event
        async def on_ready():
            """Bot startup event"""
            logger.info(f'✅ Logged in as {self.bot.user.name} ({self.bot.user.id})')
            logger.info(f'📊 Connected to {len(self.bot.guilds)} servers')

            # Load all guilds into data system and cache server info
            for guild in self.bot.guilds:
                try:
                    # Initialize guild data if needed
                    config = data_manager.load_guild_data(guild.id, "config")

                    # Cache server information for CMS access
                    config['server_name'] = guild.name
                    config['member_count'] = guild.member_count
                    config['icon_url'] = str(guild.icon.url) if guild.icon else None
                    config['owner_id'] = str(guild.owner_id)
                    config['created_at'] = guild.created_at.isoformat()

                    # Save updated config with server info
                    data_manager.save_guild_data(guild.id, "config", config)

                    logger.info(f'  - {guild.name} (ID: {guild.id}) - {guild.member_count} members')
                except Exception as e:
                    logger.error(f"Failed to initialize data for guild {guild.id}: {e}")

            # Set bot status
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(self.bot.guilds)} servers | !help"
                )
            )

        @self.bot.event
        async def on_guild_join(guild):
            """When bot joins a new server"""
            logger.info(f"📥 Joined new server: {guild.name} (ID: {guild.id})")

            # Initialize default configuration for new guild
            try:
                config = data_manager.load_guild_data(guild.id, "config")
                data_manager.create_backup(guild.id)

                # Try to send welcome message
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        embed = discord.Embed(
                            title="👋 Thanks for adding me!",
                            description=(
                                "I'm a multi-server bot with isolated data per server!\n\n"
                                f"**Default Prefix:** `!`\n"
                                f"**Change it:** `!setprefix <new_prefix>`\n"
                                f"**Get help:** `!help`"
                            ),
                            color=0x2ecc71
                        )
                        await channel.send(embed=embed)
                        break
            except Exception as e:
                logger.error(f"Failed to initialize guild {guild.id}: {e}")

        @self.bot.event
        async def on_guild_remove(guild):
            """When bot leaves a server"""
            logger.info(f"📤 Left server: {guild.name} (ID: {guild.id})")

            # Create final backup before leaving
            try:
                data_manager.create_backup(guild.id)
            except Exception as e:
                logger.error(f"Failed to create backup for guild {guild.id}: {e}")

        @self.bot.event
        async def on_command_error(ctx, error):
            """Global error handler"""
            if isinstance(error, commands.CommandNotFound):
                return  # Ignore unknown commands

            elif isinstance(error, commands.MissingPermissions):
                await ctx.send("❌ You don't have permission to use this command!")

            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f"❌ Missing argument: `{error.param.name}`")

            elif isinstance(error, commands.BadArgument):
                await ctx.send(f"❌ Invalid argument provided!")

            else:
                logger.error(f"ERROR in command {ctx.command}: {error}")
                await ctx.send("❌ An error occurred. Please try again later.")

        @self.bot.event
        async def on_message(message):
            """Global message handler"""
            if message.author == self.bot.user:
                return

            # Process commands
            await self.bot.process_commands(message)
