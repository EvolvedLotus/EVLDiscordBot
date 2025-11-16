"""
General utility commands that work across all servers
"""

import discord
from discord.ext import commands
import platform
import psutil
from datetime import datetime
from core import data_manager
from core.utils import create_embed, add_embed_footer, format_number

class General(commands.Cog):
    """General bot commands"""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.now()

    @commands.command(name="help")
    async def help_command(self, ctx):
        """Show help menu"""
        guild_id = ctx.guild.id if ctx.guild else None

        if guild_id:
            config = data_manager.load_guild_data(guild_id, "config")
            prefix = config.get("prefix", "!")
        else:
            prefix = "!"

        embed = create_embed(
            title="🤖 Bot Commands",
            description=f"Prefix for this server: `{prefix}`",
            color=0x3498db
        )

        # Currency commands
        currency_cmds = (
            f"`{prefix}balance [@user]` - Check balance\n"
            f"`{prefix}daily` - Claim daily reward\n"
            f"`{prefix}give <@user> <amount>` - Give money to user\n"
            f"`{prefix}leaderboard` - Top richest users"
        )
        embed.add_field(name="💰 Currency", value=currency_cmds, inline=False)

        # Admin commands (only show if user is admin)
        from core.permissions import is_admin
        if ctx.guild and is_admin(ctx):
            admin_cmds = (
                f"`{prefix}setprefix <new>` - Change bot prefix\n"
                f"`{prefix}setcurrency <symbol> [name]` - Set currency\n"
                f"`{prefix}serverconfig` - View server settings\n"
                f"`{prefix}togglefeature <feature>` - Enable/disable features\n"
                f"`{prefix}backup` - Create server backup"
            )
            embed.add_field(name="⚙️ Admin", value=admin_cmds, inline=False)

        # General commands
        general_cmds = (
            f"`{prefix}ping` - Check bot latency\n"
            f"`{prefix}stats` - Bot statistics\n"
            f"`{prefix}serverinfo` - Server information"
        )
        embed.add_field(name="📊 General", value=general_cmds, inline=False)

        embed.set_footer(text=f"Server-specific data • Each server has isolated economy")

        await ctx.send(embed=embed)

    @commands.command(name="ping")
    async def ping(self, ctx):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)

        if latency < 100:
            color = 0x2ecc71
            status = "🟢 Excellent"
        elif latency < 200:
            color = 0xf1c40f
            status = "🟡 Good"
        else:
            color = 0xe74c3c
            status = "🔴 Slow"

        embed = create_embed(
            title="🏓 Pong!",
            description=f"{status}\nLatency: **{latency}ms**",
            color=color
        )

        await ctx.send(embed=embed)

    @commands.command(name="stats")
    async def stats(self, ctx):
        """Bot statistics"""
        uptime = datetime.now() - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        # Get system stats
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()

        embed = create_embed(
            title="📊 Bot Statistics",
            color=0x9b59b6
        )

        # Bot stats
        total_users = sum(guild.member_count for guild in self.bot.guilds)
        embed.add_field(name="🏢 Servers", value=f"{len(self.bot.guilds)}", inline=True)
        embed.add_field(name="👥 Users", value=f"{total_users:,}", inline=True)
        embed.add_field(name="⏱️ Uptime", value=f"{hours}h {minutes}m {seconds}s", inline=True)

        # System stats
        embed.add_field(name="💻 CPU", value=f"{cpu_percent}%", inline=True)
        embed.add_field(name="🧠 RAM", value=f"{memory.percent}%", inline=True)
        embed.add_field(name="🐍 Python", value=platform.python_version(), inline=True)

        # Data stats
        all_guilds = data_manager.get_all_guilds()
        total_currency = 0
        total_users_with_balance = 0

        for guild_id in all_guilds:
            currency_data = data_manager.load_guild_data(guild_id, "currency")
            total_currency += currency_data.get("metadata", {}).get("total_currency", 0)
            total_users_with_balance += len(currency_data.get("users", {}))

        embed.add_field(
            name="💰 Total Currency",
            value=f"${total_currency:,}",
            inline=True
        )
        embed.add_field(
            name="🏦 Users with Balance",
            value=f"{total_users_with_balance:,}",
            inline=True
        )
        embed.add_field(
            name="📁 Data Folders",
            value=f"{len(all_guilds)}",
            inline=True
        )

        await ctx.send(embed=embed)

    @commands.command(name="serverinfo")
    @commands.guild_only()
    async def serverinfo(self, ctx):
        """Information about this server"""
        guild = ctx.guild

        # Count members by status
        online = sum(1 for m in guild.members if m.status == discord.Status.online)
        idle = sum(1 for m in guild.members if m.status == discord.Status.idle)
        dnd = sum(1 for m in guild.members if m.status == discord.Status.do_not_disturb)

        embed = create_embed(
            title=f"📋 {guild.name}",
            color=0x3498db
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👑 Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="🆔 ID", value=guild.id, inline=True)
        embed.add_field(name="📅 Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)

        embed.add_field(name="👥 Members", value=guild.member_count, inline=True)
        embed.add_field(name="🟢 Online", value=online, inline=True)
        embed.add_field(name="💤 Idle/DND", value=idle + dnd, inline=True)

        embed.add_field(name="💬 Channels", value=len(guild.channels), inline=True)
        embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)

        # Bot-specific data for this server
        config = data_manager.load_guild_data(guild.id, "config")
        currency_data = data_manager.load_guild_data(guild.id, "currency")

        embed.add_field(
            name="🤖 Bot Config",
            value=(
                f"Prefix: `{config.get('prefix', '!')}`\n"
                f"Currency: {config.get('currency_symbol', '$')}\n"
                f"Users in economy: {len(currency_data.get('users', {}))}"
            ),
            inline=False
        )

        await ctx.send(embed=embed)

    @commands.command(name="botinfo")
    async def botinfo(self, ctx):
        """Information about the bot"""
        embed = create_embed(
            title="🤖 Bot Information",
            description="A multi-server Discord bot with isolated economies per server",
            color=0x3498db
        )

        embed.add_field(name="📊 Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="👥 Total Users", value=str(sum(g.member_count for g in self.bot.guilds)), inline=True)
        embed.add_field(name="⚙️ Version", value="2.0.0", inline=True)

        embed.add_field(
            name="🔧 Features",
            value="• Per-server economies\n• Customizable currency\n• Task system\n• Moderation tools\n• Automated backups",
            inline=False
        )

        embed.add_field(
            name="📚 Commands",
            value=f"Use `{ctx.prefix}help` for a list of commands",
            inline=False
        )

        add_embed_footer(embed, ctx)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(General(bot))
