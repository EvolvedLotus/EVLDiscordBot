"""
Discord slash commands for announcements
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
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
