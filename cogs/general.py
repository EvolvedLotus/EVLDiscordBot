"""
General utility commands that work across all servers
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import platform
import psutil
import logging
import asyncio
import json
import os
from datetime import datetime, timedelta
from core.utils import create_embed, add_embed_footer, format_number

logger = logging.getLogger(__name__)

class General(commands.Cog):
    """General bot commands"""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.now()
        self.reminders_file = 'data/reminders.json'
        self.reminders = self.load_reminders()

    async def cog_load(self):
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    def load_reminders(self):
        if not os.path.exists('data'):
            os.makedirs('data')
        if not os.path.exists(self.reminders_file):
            return []
        try:
            with open(self.reminders_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading reminders: {e}")
            return []

    def save_reminders(self):
        try:
            with open(self.reminders_file, 'w') as f:
                json.dump(self.reminders, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving reminders: {e}")

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        now = datetime.now().timestamp()
        to_remove = []

        for reminder in self.reminders:
            if reminder['time'] <= now:
                try:
                    user = self.bot.get_user(reminder['user_id'])
                    if not user:
                        user = await self.bot.fetch_user(reminder['user_id'])
                    
                    if user:
                        embed = discord.Embed(
                            title="⏰ Reminder!",
                            description=reminder['message'],
                            color=0xf39c12,
                            timestamp=datetime.fromtimestamp(reminder['time'])
                        )
                        await user.send(embed=embed)
                except Exception as e:
                    logger.error(f"Error sending reminder to {reminder['user_id']}: {e}")
                
                to_remove.append(reminder)
        
        if to_remove:
            for reminder in to_remove:
                self.reminders.remove(reminder)
            self.save_reminders()

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

    @commands.command(name="help")
    async def help_command(self, ctx):
        """Show help menu"""
        guild_id = ctx.guild.id if ctx.guild else None

        if guild_id:
            config = self.bot.data_manager.load_guild_data(guild_id, "config")
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
        all_guilds = self.bot.data_manager.get_all_guilds()
        total_currency = 0
        total_users_with_balance = 0

        for guild_id in all_guilds:
            currency_data = self.bot.data_manager.load_guild_data(guild_id, "currency")
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
        config = self.bot.data_manager.load_guild_data(guild.id, "config")
        currency_data = self.bot.data_manager.load_guild_data(guild.id, "currency")

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

    @app_commands.command(name="help", description="Display help information")
    @app_commands.guild_only()
    async def help_slash(self, interaction: discord.Interaction):
        """Show help menu with slash commands"""
        guild_id = interaction.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")
        prefix = config.get("prefix", "!")

        embed = create_embed(
            title="🤖 Bot Commands",
            description=f"Slash commands are also available! Use `/command` instead of `{prefix}command`",
            color=0x3498db
        )

        # Currency commands
        currency_cmds = (
            "`/balance [user]` - Check balance\n"
            "`/transfer <user> <amount> [reason]` - Send coins to user\n"
            "`/daily` - Claim daily reward\n"
            "`/give <user> <amount>` - Give money to user\n"
            "`/leaderboard` - Top richest users\n"
            "`/shop /buy /inventory /redeem` - Shop system\n"
            "`/transactions [user]` - Transaction history"
        )
        embed.add_field(name="💰 Currency & Economy", value=currency_cmds, inline=False)

        # Task commands
        task_cmds = (
            "`/tasks` - Browse available tasks\n"
            "`/mytasks` - View your active tasks & **Submit Proof**\n"
            "`/claim <task_id>` - Claim a task (or use buttons)\n"
            "`/task_submit <task_id> <proof>` - Manual submission"
        )
        embed.add_field(name="📋 Tasks", value=task_cmds, inline=False)

        # Moderation commands (show only if user is moderator)
        from core.permissions import is_moderator
        if is_moderator(interaction):
            mod_cmds = (
                "`/warn <user> <reason>` - Issue warning\n"
                "`/mute <user> <duration> <reason>` - Mute user\n"
                "`/kick <user> <reason>` - Kick user\n"
                "`/ban <user> <reason>` - Ban user\n"
                "`/unmute <user>` - Unmute user\n"
                "`/clear <amount> [user]` - Clear messages\n"
                "`/slowmode <delay>` - Set slowmode\n"
                "`/lock /unlock` - Lock/unlock channel"
            )
            embed.add_field(name="🛡️ Moderation", value=mod_cmds, inline=False)

        # General commands
        general_cmds = (
            "`/help` - This help\n"
            "`/ping` - Check bot latency\n"
            "`/stats` - Bot statistics\n"
            "`/serverinfo` - Server information\n"
            "`/userinfo [user]` - User information\n"
            "`/avatar [user]` - User avatar\n"
            "`/roleinfo <role>` - Role information\n"
            "`/poll <question> <option1> <option2> [options...]` - Create poll"
        )
        embed.add_field(name="📊 General", value=general_cmds, inline=False)

        embed.set_footer(text="💡 Tip: Use the up arrow to see command history!")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Check bot latency and response")
    async def ping_slash(self, interaction: discord.Interaction):
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

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="stats", description="View bot performance statistics")
    async def stats_slash(self, interaction: discord.Interaction):
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
        all_guilds = self.bot.data_manager.get_all_guilds()
        total_currency = 0
        total_users_with_balance = 0

        for guild_id in all_guilds:
            currency_data = self.bot.data_manager.load_guild_data(guild_id, "currency")
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

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="serverinfo", description="Display server information")
    @app_commands.guild_only()
    async def serverinfo_slash(self, interaction: discord.Interaction):
        """Information about this server"""
        guild = interaction.guild

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
        embed.add_field(name="🆔 ID", value=str(guild.id), inline=True)
        embed.add_field(name="📅 Created", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=True)

        embed.add_field(name="👥 Members", value=guild.member_count, inline=True)
        embed.add_field(name="🟢 Online", value=online, inline=True)
        embed.add_field(name="💤 Idle/DND", value=idle + dnd, inline=True)

        embed.add_field(name="💬 Channels", value=len(guild.channels), inline=True)
        embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)

        # Bot-specific data for this server
        config = self.bot.data_manager.load_guild_data(guild.id, "config")
        currency_data = self.bot.data_manager.load_guild_data(guild.id, "currency")

        embed.add_field(
            name="🤖 Bot Config",
            value=(
                f"Prefix: `{config.get('prefix', '!')}`\n"
                f"Currency: {config.get('currency_symbol', '$')}\n"
                f"Users in economy: {len(currency_data.get('users', {}))}"
            ),
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="userinfo", description="Display user information")
    @app_commands.describe(user="User to check (defaults to yourself)")
    @app_commands.guild_only()
    async def userinfo_slash(self, interaction: discord.Interaction, user: discord.Member = None):
        """Display user information"""
        target = user or interaction.user

        embed = create_embed(
            title=f"👤 {target.display_name}",
            color=target.color if target.color != discord.Color.default() else 0x3498db
        )

        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)

        embed.add_field(name="📛 Username", value=f"{target.name}#{target.discriminator}", inline=True)
        embed.add_field(name="🆔 ID", value=str(target.id), inline=True)
        embed.add_field(name="🤖 Bot?", value="Yes" if target.bot else "No", inline=True)

        embed.add_field(name="📅 Joined Discord", value=f"<t:{int(target.created_at.timestamp())}:F>", inline=False)
        embed.add_field(name="📅 Joined Server", value=f"<t:{int(target.joined_at.timestamp())}:F>", inline=True)

        # Role info
        roles = [role for role in target.roles if role.name != "@everyone"]
        if roles:
            role_list = ", ".join([f"<@&{role.id}>" for role in roles[:5]])  # Max 5 roles in field
            if len(roles) > 5:
                role_list += f" +{len(roles) - 5} more"
            embed.add_field(name="🎭 Roles", value=role_list, inline=False)

        # Bot-specific data
        currency_data = self.bot.data_manager.load_guild_data(interaction.guild.id, "currency")
        user_balance = currency_data.get("users", {}).get(str(target.id), {}).get("balance", 0)
        config = self.bot.data_manager.load_guild_data(interaction.guild.id, "config")
        symbol = config.get("currency_symbol", "$")

        embed.add_field(
            name="💰 Balance",
            value=f"{symbol}{user_balance:,}",
            inline=True
        )

        # Activity status
        if target.activity:
            embed.add_field(name="🎮 Activity", value=str(target.activity.name), inline=True)
        else:
            embed.add_field(name="🎮 Activity", value="None", inline=True)

        embed.set_footer(text=f"Requested by {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="avatar", description="Display user avatar (large)")
    @app_commands.describe(user="User to show avatar for (defaults to yourself)")
    async def avatar_slash(self, interaction: discord.Interaction, user: discord.Member = None):
        """Display user avatar in large format"""
        target = user or interaction.user

        # Check if user has avatar
        if not target.avatar:
            embed = create_embed(
                title=f"🖼️ {target.display_name}'s Avatar",
                description="This user doesn't have a custom avatar.",
                color=0x3498db
            )
            embed.set_image(url=target.default_avatar.url)
        else:
            embed = create_embed(
                title=f"🖼️ {target.display_name}'s Avatar",
                color=target.color if target.color != discord.Color.default() else 0x3498db
            )
            embed.set_image(url=target.avatar.url)

        embed.add_field(name="📛 Username", value=f"{target.name}#{target.discriminator}", inline=True)
        embed.add_field(name="🔗 Direct Link", value=f"[Click here]({target.avatar.url if target.avatar else target.default_avatar.url})", inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="Display role information")
    @app_commands.describe(role="Role to display information for")
    @app_commands.guild_only()
    async def roleinfo_slash(self, interaction: discord.Interaction, role: discord.Role):
        """Display detailed role information"""
        embed = create_embed(
            title=f"🎭 Role: {role.name}",
            color=role.color
        )

        embed.add_field(name="🆔 ID", value=str(role.id), inline=True)
        embed.add_field(name="🎨 Color", value=str(role.color), inline=True)
        embed.add_field(name="📍 Position", value=str(role.position), inline=True)

        permissions = []
        if role.permissions.administrator:
            permissions.append("Administrator")
        else:
            if role.permissions.manage_channels:
                permissions.append("Manage Channels")
            if role.permissions.manage_roles:
                permissions.append("Manage Roles")
            if role.permissions.kick_members:
                permissions.append("Kick Members")
            if role.permissions.ban_members:
                permissions.append("Ban Members")
            if role.permissions.manage_messages:
                permissions.append("Manage Messages")

        embed.add_field(
            name="🔒 Key Permissions",
            value=", ".join(permissions) if permissions else "None",
            inline=False
        )

        embed.add_field(name="👥 Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="📌 Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="📈 Hoisted", value="Yes" if role.hoist else "No", inline=True)

        embed.add_field(name="📅 Created", value=f"<t:{int(role.created_at.timestamp())}:F>", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="poll", description="Create polls with up to 10 options")
    @app_commands.describe(
        question="The poll question",
        option1="First option",
        option2="Second option",
        option3="Third option (optional)",
        option4="Fourth option (optional)",
        option5="Fifth option (optional)",
        option6="Sixth option (optional)",
        option7="Seventh option (optional)",
        option8="Eighth option (optional)",
        option9="Ninth option (optional)",
        option10="Tenth option (optional)"
    )
    @app_commands.guild_only()
    async def poll_slash(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: str = None,
        option4: str = None,
        option5: str = None,
        option6: str = None,
        option7: str = None,
        option8: str = None,
        option9: str = None,
        option10: str = None
    ):
        """Create a poll with up to 10 options"""
        # Collect all non-None options
        options = [opt for opt in [option1, option2, option3, option4, option5, option6, option7, option8, option9, option10] if opt is not None]

        if len(options) < 2:
            await interaction.response.send_message("❌ Polls must have at least 2 options!", ephemeral=True)
            return

        if len(options) > 10:
            await interaction.response.send_message("❌ Polls can have maximum 10 options!", ephemeral=True)
            return

        # Validate question length
        if len(question) > 256:
            await interaction.response.send_message("❌ Question too long! Maximum 256 characters.", ephemeral=True)
            return

        # Validate option lengths
        for i, option in enumerate(options):
            if len(option) > 100:
                await interaction.response.send_message(f"❌ Option {i+1} too long! Maximum 100 characters.", ephemeral=True)
                return

        # Create poll embed
        embed = discord.Embed(
            title=f"📊 Poll: {question}",
            description=f"Created by {interaction.user.mention}",
            color=0x3498db,
            timestamp=datetime.now()
        )

        # Add options with reactions
        reaction_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        option_text = ""

        for i, option in enumerate(options):
            emoji = reaction_emojis[i]
            option_text += f"{emoji} {option}\n"
            embed.add_field(name=f"Option {i+1}", value=option, inline=False)

        embed.set_footer(text="Vote by clicking the numbers below!")

        # Send the embed
        try:
            await interaction.response.send_message(embed=embed)
            message = await interaction.original_response()

            # Add reactions
            for i in range(len(options)):
                emoji = reaction_emojis[i]
                await message.add_reaction(emoji)

        except discord.HTTPException as e:
            logger.error(f"Error creating poll: {e}")
            await interaction.response.send_message("❌ Error creating poll. Please try again.", ephemeral=True)

    @app_commands.command(name="remind", description="Set personal reminder")
    @app_commands.describe(
        time="Time until reminder (e.g., 1h, 30m, 2d)",
        message="Reminder message"
    )
    @app_commands.guild_only()
    async def remind_slash(self, interaction: discord.Interaction, time: str, message: str):
        """Set a personal reminder"""
        # Parse time
        import re

        time_regex = re.compile(r'^(\d+)([smhd])$', re.IGNORECASE)
        match = time_regex.match(time.strip())

        if not match:
            await interaction.response.send_message(
                "❌ Invalid time format! Use formats like: `30s`, `5m`, `2h`, `1d`",
                ephemeral=True
            )
            return

        amount = int(match.group(1))
        unit = match.group(2).lower()

        # Convert to seconds
        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        total_seconds = amount * multipliers[unit]

        # Validate limits
        if total_seconds < 30:  # Minimum 30 seconds
            await interaction.response.send_message("❌ Reminders must be at least 30 seconds in the future!", ephemeral=True)
            return
        if total_seconds > 604800:  # Maximum 7 days
            await interaction.response.send_message("❌ Reminders cannot be more than 7 days in the future!", ephemeral=True)
            return

        # Validate message length
        if len(message) > 500:
            await interaction.response.send_message("❌ Reminder message too long! Maximum 500 characters.", ephemeral=True)
            return

        # Calculate reminder time
        reminder_time = datetime.now() + timedelta(seconds=total_seconds)

        embed = discord.Embed(
            title="⏰ Reminder Set!",
            description=f"I'll remind you in {amount}{unit} about:",
            color=0xf39c12
        )
        embed.add_field(name="💭 Message", value=message, inline=False)
        embed.add_field(name="🕐 Remind Time", value=f"<t:{int(reminder_time.timestamp())}:R>", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Store reminder
        self.reminders.append({
            'user_id': interaction.user.id,
            'message': message,
            'time': reminder_time.timestamp()
        })
        self.save_reminders()
        
        logger.info(f"Reminder set for {interaction.user.id}: '{message}' at {reminder_time}")

    @app_commands.command(name="clear_channel", description="Clear all messages in channel (Admin only)")
    @app_commands.guild_only()
    async def clear_channel_slash(self, interaction: discord.Interaction):
        """Clear all messages in the current channel (Admin only)"""
        # Check admin permissions
        from core.permissions import is_admin_interaction
        if not is_admin_interaction(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
            return

        # Check bot permissions
        if not interaction.guild.me.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ I don't have permission to manage messages!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Get channel
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ This command can only be used in text channels!", ephemeral=True)
            return

        try:
            # Purge all messages (limit to 1000 due to Discord API limits)
            deleted = await channel.purge(limit=1000, before=interaction.created_at)

            embed = discord.Embed(
                title="🗑️ Channel Cleared",
                description=f"Successfully deleted {len(deleted)} messages from {channel.mention}",
                color=discord.Color.red()
            )
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Channel", value=channel.mention, inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.HTTPException as e:
            logger.error(f"Error clearing chat: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to clear messages. Some messages may be too old to delete (older than 2 weeks).",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Unexpected error in clear_chat: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An unexpected error occurred while clearing the channel.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    # NOTE: /chat command removed - use /chat from ai_cog.py for AI conversations instead
    # If you need to send messages as the bot, use the web CMS or create a new command like /say


async def setup(bot):
    await bot.add_cog(General(bot))

