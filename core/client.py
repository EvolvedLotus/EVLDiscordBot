"""
Discord client initialization and configuration
"""

import discord
from discord.ext import commands
import os
from .data_manager import DataManager

# Global data manager instance - will be set by bot.py
data_manager = None

def create_bot() -> commands.Bot:
    """Create and configure the Discord bot"""

    # Load environment variables (only for local development)
    if os.getenv('ENVIRONMENT') != 'production':
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass  # dotenv not installed in production

    TOKEN = os.getenv('DISCORD_TOKEN')

    if not TOKEN:
        raise ValueError("DISCORD_TOKEN not found in environment variables")

    # Bot intents
    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True

    # Create bot with dynamic prefix support
    bot = commands.Bot(
        command_prefix=get_prefix,
        intents=intents,
        help_command=None,
        case_insensitive=True
    )

    return bot, TOKEN

async def get_prefix(bot, message):
    """Get server-specific prefix dynamically"""
    if not message.guild:
        return "!"  # Default for DMs

    try:
        config = data_manager.load_guild_data(message.guild.id, "config")
        return config.get("prefix", "!")
    except Exception:
        return "!"  # Fallback

def get_token() -> str:
    """Get Discord bot token from environment"""
    # Load environment variables (only for local development)
    if os.getenv('ENVIRONMENT') != 'production':
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass  # dotenv not installed in production

    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise ValueError("DISCORD_TOKEN not found in environment variables")
    return token
