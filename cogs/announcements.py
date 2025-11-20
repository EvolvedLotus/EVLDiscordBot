"""
Discord slash commands for announcements
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from datetime import datetime, timedelta
from core.announcement_manager import AnnouncementManager

class Announcements(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Use global data_manager instead of self.bot.data_manager to avoid timing issues
        from core import data_manager
        self.announcement_manager = AnnouncementManager(data_manager, bot)

    @app_commands.command(name="announce", description="Create an announcement")
    @app_commands.describe(
        title="Announcement title",
        content="Announcement content",
        channel="Channel to post in (defaults to current)",
        mention_everyone="Mention @everyone",
        pin="Pin the announcement"
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        channel: Optional[discord.TextChannel] = None,
        mention_everyone: bool = False,
        pin: bool = False
    ):
        """Create and post announcement"""
        await interaction.response.defer(ephemeral=True)

        # Permission check
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ You need administrator permissions to create announcements.", ephemeral=True)
            return

        target_channel = channel or interaction.channel
        guild_id = str(interaction.guild_id)

        try:
            mentions = {"everyone": mention_everyone, "roles": [], "users": []}

            announcement = await self.announcement_manager.create_announcement(
                guild_id=guild_id,
                title=title,
                content=content,
                channel_id=str(target_channel.id),
                author_id=str(interaction.user.id),
                author_name=interaction.user.display_name,
                announcement_type="general",
                mentions=mentions,
                auto_pin=pin
            )

            await interaction.followup.send(
                f"✅ Announcement created successfully!\n"
                f"ID: `{announcement['id']}`\n"
                f"Channel: {target_channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create announcement: {str(e)}", ephemeral=True)

    @app_commands.command(name="announce-task", description="Post announcement for a task")
    @app_commands.describe(
        task_id="Task ID to announce",
        channel="Channel to post in (defaults to task channel)",
        pin="Pin the announcement"
    )
    async def announce_task(
        self,
        interaction: discord.Interaction,
        task_id: str,
        channel: Optional[discord.TextChannel] = None,
        pin: Optional[bool] = None
    ):
        """Create task announcement"""
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ You need administrator permissions.", ephemeral=True)
            return

        guild_id = str(interaction.guild_id)

        # Load task to get default channel
        task_data = self.bot.data_manager.load_guild_data(guild_id, "tasks")
        if not task_data or task_id not in task_data.get("tasks", {}):
            await interaction.followup.send(f"❌ Task `{task_id}` not found.", ephemeral=True)
            return

        task = task_data["tasks"][task_id]
        target_channel = channel or interaction.guild.get_channel(int(task.get("channel_id", interaction.channel.id)))

        try:
            announcement = await self.announcement_manager.create_task_announcement(
                guild_id=guild_id,
                task_id=task_id,
                channel_id=str(target_channel.id),
                author_id=str(interaction.user.id),
                author_name=interaction.user.display_name,
                auto_pin=pin
            )

            await interaction.followup.send(
                f"✅ Task announcement posted!\n"
                f"Task: **{task['name']}**\n"
                f"Channel: {target_channel.mention}\n"
                f"ID: `{announcement['id']}`",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create task announcement: {str(e)}", ephemeral=True)

    @app_commands.command(name="scheduleannouncement", description="Schedule an announcement to be posted later")
    @app_commands.describe(
        title="Announcement title",
        content="Announcement content",
        delay_minutes="Delay in minutes before posting",
        channel="Channel to post in (defaults to current)",
        mention_everyone="Mention @everyone",
        pin="Pin the announcement when posted"
    )
    async def scheduleannouncement(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        delay_minutes: int,
        channel: Optional[discord.TextChannel] = None,
        mention_everyone: bool = False,
        pin: bool = False
    ):
        """Schedule an announcement to be posted later"""
        await interaction.response.defer(ephemeral=True)

        # Permission check
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ You need administrator permissions to schedule announcements.", ephemeral=True)
            return

        # Validate delay
        if delay_minutes < 1:
            await interaction.followup.send("❌ Delay must be at least 1 minute.", ephemeral=True)
            return
        if delay_minutes > 1440:  # Max 24 hours
            await interaction.followup.send("❌ Maximum delay is 1440 minutes (24 hours).", ephemeral=True)
            return

        target_channel = channel or interaction.channel
        guild_id = str(interaction.guild_id)
        schedule_time = datetime.now() + timedelta(minutes=delay_minutes)

        try:
            # Store the scheduled announcement in data
            schedule_data = {
                'id': f"scheduled_{int(datetime.now().timestamp() * 1000)}",
                'title': title,
                'content': content,
                'channel_id': str(target_channel.id),
                'scheduled_for': schedule_time.isoformat(),
                'delay_minutes': delay_minutes,
                'author_id': str(interaction.user.id),
                'author_name': interaction.user.display_name,
                'mention_everyone': mention_everyone,
                'auto_pin': pin,
                'status': 'scheduled'
            }

            # Load existing scheduled announcements
            announcements_data = self.bot.data_manager.load_guild_data(guild_id, 'announcements') or {'scheduled': []}

            # Add to scheduled list
            if 'scheduled' not in announcements_data:
                announcements_data['scheduled'] = []
            announcements_data['scheduled'].append(schedule_data)

            # Save back
            self.bot.data_manager.save_guild_data(guild_id, 'announcements', announcements_data)

            embed = discord.Embed(
                title="⏰ Announcement Scheduled",
                color=discord.Color.blue()
            )
            embed.add_field(name="Title", value=title, inline=False)
            embed.add_field(name="Channel", value=target_channel.mention, inline=True)
            embed.add_field(name="Scheduled For", value=f"<t:{int(schedule_time.timestamp())}:R> ({delay_minutes} minutes)", inline=True)
            embed.add_field(name="ID", value=f"`{schedule_data['id']}`", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to schedule announcement: {str(e)}", ephemeral=True)

    @app_commands.command(name="create_embed", description="Create a custom embed message")
    @app_commands.describe(
        title="Embed title",
        description="Embed description/content",
        color="Embed color (hex code, optional)",
        channel="Channel to post in (defaults to current)"
    )
    async def create_embed(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None
    ):
        """Create and post a custom embed message"""
        await interaction.response.defer(ephemeral=True)

        # Permission check
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ You need administrator permissions to create embeds.", ephemeral=True)
            return

        target_channel = channel or interaction.channel

        try:
            # Parse color if provided
            embed_color = discord.Color.blue()  # Default
            if color:
                try:
                    # Remove # if present and convert hex to int
                    hex_color = color.lstrip('#')
                    embed_color = discord.Color(int(hex_color, 16))
                except ValueError:
                    await interaction.followup.send("❌ Invalid color format. Use hex code like #FF0000.", ephemeral=True)
                    return

            # Create the embed
            embed = discord.Embed(
                title=title,
                description=description,
                color=embed_color,
                timestamp=datetime.now()
            )
            embed.set_footer(text=f"Created by {interaction.user.display_name}")

            # Post the embed
            await target_channel.send(embed=embed)

            await interaction.followup.send(
                f"✅ Embed created successfully!\n"
                f"Channel: {target_channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create embed: {str(e)}", ephemeral=True)

    @app_commands.command(name="create_rich_embed", description="Create a rich embed with fields and customizations")
    @app_commands.describe(
        title="Embed title",
        description="Main embed description",
        field1_title="First field title (optional)",
        field1_value="First field value (optional)",
        field2_title="Second field title (optional)",
        field2_value="Second field value (optional)",
        color="Embed color (hex code, optional)",
        thumbnail_url="Thumbnail image URL (optional)",
        channel="Channel to post in (defaults to current)"
    )
    async def create_rich_embed(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        field1_title: Optional[str] = None,
        field1_value: Optional[str] = None,
        field2_title: Optional[str] = None,
        field2_value: Optional[str] = None,
        color: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None
    ):
        """Create a rich embed with multiple fields and customizations"""
        await interaction.response.defer(ephemeral=True)

        # Permission check
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ You need administrator permissions to create embeds.", ephemeral=True)
            return

        target_channel = channel or interaction.channel

        try:
            # Parse color if provided
            embed_color = discord.Color.blue()  # Default
            if color:
                try:
                    hex_color = color.lstrip('#')
                    embed_color = discord.Color(int(hex_color, 16))
                except ValueError:
                    await interaction.followup.send("❌ Invalid color format. Use hex code like #FF0000.", ephemeral=True)
                    return

            # Create the embed
            embed = discord.Embed(
                title=title,
                description=description,
                color=embed_color,
                timestamp=datetime.now()
            )

            # Add fields if provided
            if field1_title and field1_value:
                embed.add_field(name=field1_title, value=field1_value, inline=False)
            if field2_title and field2_value:
                embed.add_field(name=field2_title, value=field2_value, inline=False)

            # Add thumbnail if provided
            if thumbnail_url:
                try:
                    embed.set_thumbnail(url=thumbnail_url)
                except Exception:
                    # Ignore invalid URLs
                    pass

            embed.set_footer(text=f"Created by {interaction.user.display_name}")

            # Post the embed
            await target_channel.send(embed=embed)

            await interaction.followup.send(
                f"✅ Rich embed created successfully!\n"
                f"Channel: {target_channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create rich embed: {str(e)}", ephemeral=True)

    @app_commands.command(name="pin-announcement", description="Pin an announcement")
    @app_commands.describe(announcement_id="Announcement ID to pin")
    async def pin_announcement(self, interaction: discord.Interaction, announcement_id: str):
        """Pin announcement message"""
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.guild_permissions.manage_messages:
            await interaction.followup.send("❌ You need manage messages permission.", ephemeral=True)
            return

        try:
            success = await self.announcement_manager.pin_announcement(
                str(interaction.guild_id),
                announcement_id
            )

            if success:
                await interaction.followup.send(f"✅ Announcement `{announcement_id}` pinned!", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to pin announcement.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="unpin-announcement", description="Unpin an announcement")
    @app_commands.describe(announcement_id="Announcement ID to unpin")
    async def unpin_announcement(self, interaction: discord.Interaction, announcement_id: str):
        """Unpin announcement message"""
        await interaction.response.defer(ephemeral=True)

        if not interaction.user.guild_permissions.manage_messages:
            await interaction.followup.send("❌ You need manage messages permission.", ephemeral=True)
            return

        try:
            success = await self.announcement_manager.unpin_announcement(
                str(interaction.guild_id),
                announcement_id
            )

            if success:
                await interaction.followup.send(f"✅ Announcement `{announcement_id}` unpinned!", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to unpin announcement.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Announcements(bot))
