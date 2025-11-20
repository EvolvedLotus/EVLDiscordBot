"""
Admin commands for server-specific configuration
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import asyncio
import logging
from core.permissions import admin_only, admin_only_interaction, feature_enabled, is_moderator, is_moderator_interaction
from core.utils import create_embed, add_embed_footer
from core.validator import DataValidator, Validator
from core.initializer import GuildInitializer
from core.shop_manager import ShopManager

logger = logging.getLogger(__name__)

# Suppress some DiscordPY warnings
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="discord")

class Admin(commands.Cog):
    """Server administration commands"""

    def __init__(self, bot):
        self.bot = bot
        # Initialize shop_manager lazily to avoid dependency issues during cog loading
        self._shop_manager = None

    @property
    def shop_manager(self):
        if self._shop_manager is None:
            currency_cog = self.bot.get_cog('Currency')
            if currency_cog:
                self._shop_manager = ShopManager(self.bot.data_manager, currency_cog.transaction_manager)
            else:
                # Fallback if Currency cog not available
                self._shop_manager = None
        return self._shop_manager

    def _get_item_emoji(self, item: dict) -> str:
        """Get emoji from item, handling missing emoji field gracefully"""
        emoji = item.get('emoji')
        if emoji:
            return emoji

        # Try to extract emoji from name
        name = item.get('name', '')
        if name and any(ord(c) > 127 for c in name[:5]):  # Check for unicode emoji
            extracted = ''.join(c for c in name[:5] if ord(c) > 127)
            if extracted:
                return extracted

        return '🛍️'  # Default shopping bag emoji

    @app_commands.command(name="setprefix", description="Change the bot prefix for this server")
    @app_commands.guild_only()
    @admin_only_interaction()
    async def set_prefix(self, interaction: discord.Interaction, new_prefix: str):
        """Change bot prefix for THIS server"""
        if len(new_prefix) > 5:
            await interaction.response.send_message("❌ Prefix too long! Maximum 5 characters.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        config = self.bot.data_manager.load_guild_data(guild_id, "config")

        old_prefix = config.get("prefix", "!")
        config["prefix"] = new_prefix

        self.bot.data_manager.save_guild_data(guild_id, "config", config)

        embed = create_embed(
            title="✅ Prefix Changed",
            description=f"Changed from `{old_prefix}` to `{new_prefix}`",
            color=0x2ecc71
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="completetask", description="Mark a task as completed and award reward")
    @app_commands.describe(
        task_id="ID of the task to complete",
        user="User who completed the task (leave empty for current user)"
    )
    @app_commands.guild_only()
    @admin_only_interaction()
    async def complete_task(
        self,
        interaction: discord.Interaction,
        task_id: str,
        user: discord.Member = None
    ):
        """Mark a task as completed and award the reward"""
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id
        tasks_data = self.bot.data_manager.load_guild_data(guild_id, "tasks")

        # Find the task
        tasks = tasks_data.get("tasks", {})
        if task_id not in tasks:
            await interaction.followup.send("❌ Task not found!", ephemeral=True)
            return

        task = tasks[task_id]

        # Check if task is pending or claimed
        if task.get("status") not in ["pending", "claimed"]:
            await interaction.followup.send("❌ Task is not available for completion!", ephemeral=True)
            return

        # Determine the user who completed the task
        completing_user = user or interaction.user

        # If task is claimed, check if it's claimed by the specified user
        user_tasks = tasks_data.get("user_tasks", {})
        if str(completing_user.id) not in user_tasks:
            user_tasks[str(completing_user.id)] = {}

        user_task_data = user_tasks[str(completing_user.id)].get(task_id)
        if not user_task_data:
            # Task not claimed, create user task entry
            user_task_data = {
                "claimed_at": datetime.now().isoformat(),
                "deadline": (datetime.now() + timedelta(hours=task.get("duration_hours", 24))).isoformat(),
                "status": "completed"
            }
            user_tasks[str(completing_user.id)][task_id] = user_task_data
        else:
            # Update existing user task
            user_task_data["status"] = "completed"

        # Award the reward
        currency_cog = self.bot.get_cog('Currency')
        if currency_cog:
            reward = task.get("reward", 0)
            currency_cog._add_balance(
                guild_id,
                completing_user.id,
                reward,
                f"Task completed: {task.get('name', 'Unknown task')}"
            )

            # Update task status
            task["status"] = "completed"
            task["completed_by"] = str(completing_user.id)
            task["completed_at"] = datetime.now().isoformat()

            # Save data atomically
            updates = {
                "tasks": tasks_data,
                "currency": self.bot.data_manager.load_guild_data(guild_id, "currency"),
                "transactions": self.bot.data_manager.load_guild_data(guild_id, "transactions")
            }

            success = self.bot.data_manager.atomic_transaction(guild_id, updates)

            if success:
                # Update Discord message
                await self._update_task_message(guild_id, task_id, task)

                # Send notification to user
                try:
                    config = self.bot.data_manager.load_guild_data(guild_id, "config")
                    symbol = config.get('currency_symbol', '$')

                    embed = discord.Embed(
                        title="✅ Task Completed!",
                        description=f"You have completed **{task.get('name', 'Unknown task')}**",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Reward", value=f"{symbol}{reward}", inline=True)
                    embed.add_field(name="Task ID", value=f"`{task_id}`", inline=True)

                    await completing_user.send(embed=embed)
                except discord.Forbidden:
                    pass  # Can't DM user

                # Send success message
                embed = discord.Embed(
                    title="✅ Task Completed",
                    description=f"Task **{task.get('name', 'Unknown task')}** marked as completed",
                    color=discord.Color.green()
                )
                embed.add_field(name="User", value=completing_user.mention, inline=True)
                embed.add_field(name="Reward", value=f"{symbol}{reward}", inline=True)
                embed.add_field(name="Task ID", value=f"`{task_id}`", inline=True)

                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to complete task - data save error!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Currency system not available!", ephemeral=True)

    async def _update_task_message(self, guild_id: int, task_id: str, task_data: dict):
        """Update the Discord message for a completed task"""
        try:
            message_id = task_data.get("message_id")
            if not message_id:
                return

            config = self.bot.data_manager.load_guild_data(guild_id, "config")
            task_channel_id = config.get("task_channel_id")
            if not task_channel_id:
                return

            guild = self.bot.get_guild(guild_id)
            if not guild:
                return

            channel = guild.get_channel(int(task_channel_id))
            if not channel:
                return

            message = await channel.fetch_message(int(message_id))

            # Create updated embed
            embed = discord.Embed(
                title=f"✅ {task_data['name']}",
                description=task_data.get('description', 'No description'),
                color=discord.Color.green()
            )

            embed.add_field(name="Reward", value=f"💰 {task_data['reward']} coins", inline=True)
            embed.add_field(name="Status", value="✅ Completed", inline=True)

            duration = task_data.get('duration_hours', 24)
            embed.add_field(name="Time Limit", value=f"⏰ {duration} hours", inline=True)

            completed_by_id = task_data.get("completed_by")
            if completed_by_id:
                completed_by = guild.get_member(int(completed_by_id))
                if completed_by:
                    embed.add_field(name="Completed By", value=completed_by.mention, inline=True)

            embed.set_footer(text=f"Task ID: {task_id} | ✅ COMPLETED")

            await message.edit(embed=embed)

        except Exception as e:
            logger.error(f"Failed to update task message for {task_id}: {e}")


class DeleteConfirmView(discord.ui.View):
    """Confirmation buttons for item deletion"""

    def __init__(self, shop_manager, guild_id, item_id, archive, item):
        super().__init__(timeout=60)
        self.shop_manager = shop_manager
        self.guild_id = guild_id
        self.item_id = item_id
        self.archive = archive
        self.item = item

    def _get_item_emoji(self, item: dict) -> str:
        """Get emoji from item, handling missing emoji field gracefully"""
        emoji = item.get('emoji')
        if emoji:
            return emoji

        # Try to extract emoji from name
        name = item.get('name', '')
        if name and any(ord(c) > 127 for c in name[:5]):  # Check for unicode emoji
            extracted = ''.join(c for c in name[:5] if ord(c) > 127)
            if extracted:
                return extracted

        return '🛍️'  # Default shopping bag emoji

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Execute deletion"""
        try:
            success = self.shop_manager.delete_item(self.guild_id, self.item_id, self.archive)

            if success:
                embed = discord.Embed(
                    title="✅ Item Deleted",
                    description=f"**{self._get_item_emoji(self.item)} {self.item['name']}** has been {'archived' if self.archive else 'permanently deleted'}",
                    color=discord.Color.red()
                )
                embed.add_field(name="Item ID", value=f"`{self.item_id}`", inline=True)
                embed.add_field(name="Action", value="Archived" if self.archive else "Deleted", inline=True)
            else:
                embed = discord.Embed(
                    title="❌ Deletion Failed",
                    description="Item could not be deleted",
                    color=discord.Color.red()
                )

            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()

        except discord.NotFound as e:
            # Handle expired interactions (10062: Unknown interaction)
            if "10062" in str(e) or "Unknown interaction" in str(e):
                try:
                    # Send a new message since the interaction expired
                    embed = discord.Embed(
                        title="✅ Item Deleted",
                        description=f"**{self._get_item_emoji(self.item)} {self.item['name']}** has been {'archived' if self.archive else 'permanently deleted'}",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="Item ID", value=f"`{self.item_id}`", inline=True)
                    embed.add_field(name="Action", value="Archived" if self.archive else "Deleted", inline=True)
                    embed.add_field(name="Note", value="⚠️ This confirmation took longer than expected", inline=False)

                    # Try to send to the interaction user directly
                    await interaction.user.send(embed=embed)
                except discord.Forbidden:
                    # Can't DM user, try to send in channel if possible
                    try:
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    except:
                        pass  # Last resort - just log the success
                logger.info(f"Shop item '{self.item_id}' deleted successfully (interaction expired)")
            else:
                # Re-raise if it's a different NotFound error
                raise
        except Exception as e:
            # Handle other exceptions
            error_embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            try:
                await interaction.response.edit_message(embed=error_embed, view=None)
            except discord.NotFound:
                # If interaction is expired, send followup
                try:
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                except:
                    pass
            self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel deletion"""
        await interaction.response.edit_message(
            content="Deletion cancelled.",
            embed=None,
            view=None
        )
        self.stop()


async def setup(bot):
    await bot.add_cog(Admin(bot))
