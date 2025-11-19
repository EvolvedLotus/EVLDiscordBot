import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Dict, List, Optional
from core.permissions import admin_only_interaction, moderator_only_interaction

logger = logging.getLogger(__name__)

class ModerationCommands(commands.Cog):
    """Additional moderation commands and utilities"""

    def __init__(self, bot):
        self.bot = bot
        self.moderation_cog = None  # Will be set after cogs are loaded

    def set_moderation_cog(self, moderation_cog):
        """Set reference to the main moderation cog"""
        self.moderation_cog = moderation_cog

    @app_commands.command(name="warn", description="Issue a warning to a user")
    @moderator_only_interaction()
    async def warn_user(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        """Manually warn a user"""
        try:
            if not self.moderation_cog:
                await interaction.response.send_message("Moderation system not available", ephemeral=True)
                return

            result = await self.moderation_cog.actions.warn_user(
                interaction.guild.id, user.id, reason, interaction.user.id, auto_generated=False
            )

            if result['success']:
                embed = discord.Embed(
                    title="⚠️ User Warned",
                    description=f"Successfully warned {user.mention}",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                if result.get('dm_sent'):
                    embed.add_field(name="DM Sent", value="✅", inline=True)
                else:
                    embed.add_field(name="DM Sent", value="❌ (DMs disabled)", inline=True)
            else:
                embed = discord.Embed(
                    title="❌ Warning Failed",
                    description=result.get('error', 'Unknown error'),
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error warning user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while warning the user",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="mute", description="Temporarily mute a user")
    @moderator_only_interaction()
    async def mute_user(self, interaction: discord.Interaction, user: discord.Member,
                       duration: int, reason: str):
        """Temporarily mute a user for specified minutes"""
        try:
            if not self.moderation_cog:
                await interaction.response.send_message("Moderation system not available", ephemeral=True)
                return

            result = await self.moderation_cog.actions.apply_temporary_mute(
                interaction.guild.id, user.id, duration * 60, reason, interaction.user.id
            )

            if result['success']:
                embed = discord.Embed(
                    title="🔇 User Muted",
                    description=f"Successfully muted {user.mention} for {duration} minutes",
                    color=discord.Color.yellow()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Duration", value=f"{duration} minutes", inline=True)
            else:
                embed = discord.Embed(
                    title="❌ Mute Failed",
                    description=result.get('error', 'Unknown error'),
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error muting user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while muting the user",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="kick", description="Kick a user from the server")
    @moderator_only_interaction()
    async def kick_user(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        """Kick a user from the server"""
        try:
            # Check permissions
            if not interaction.guild.me.guild_permissions.kick_members:
                await interaction.response.send_message("❌ I don't have permission to kick members!", ephemeral=True)
                return

            # Prevent self-kicking
            if user.id == interaction.user.id:
                await interaction.response.send_message("❌ You cannot kick yourself!", ephemeral=True)
                return

            # Prevent kicking bots
            if user.bot:
                await interaction.response.send_message("❌ You cannot kick bots!", ephemeral=True)
                return

            try:
                await user.kick(reason=reason)
                embed = discord.Embed(
                    title="👢 User Kicked",
                    description=f"Successfully kicked {user.mention}",
                    color=discord.Color.red()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Kicked By", value=interaction.user.mention, inline=True)

                # Send DM notification to the kicked user
                try:
                    dm_embed = discord.Embed(
                        title="👢 You were kicked",
                        description=f"You were kicked from **{interaction.guild.name}**",
                        color=discord.Color.red()
                    )
                    dm_embed.add_field(name="Reason", value=reason, inline=False)
                    dm_embed.add_field(name="Kicked By", value=interaction.user.mention, inline=True)
                    await user.send(embed=dm_embed)
                    embed.add_field(name="DM Sent", value="✅", inline=True)
                except discord.Forbidden:
                    embed.add_field(name="DM Sent", value="❌ (DMs disabled)", inline=True)

                # Log the kick in moderation audit
                if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                    self.moderation_cog.logger.create_moderation_audit_log(
                        interaction.guild.id, 'kick', user.id, interaction.user.id,
                        details={'reason': reason}
                    )

            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Kick Failed",
                    description="I don't have permission to kick this user",
                    color=discord.Color.red()
                )
            except discord.HTTPException as e:
                embed = discord.Embed(
                    title="❌ Kick Failed",
                    description=f"Failed to communicate with Discord: {e}",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error kicking user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while kicking the user",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unmute", description="Remove timeout/mute from a user")
    @moderator_only_interaction()
    async def unmute_user(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Moderator action"):
        """Remove timeout/mute from a user"""
        try:
            # Check permissions
            if not interaction.guild.me.guild_permissions.moderate_members:
                await interaction.response.send_message("❌ I don't have permission to moderate members!", ephemeral=True)
                return

            # Check if user is actually timed out
            if user.communication_disabled_until is None:
                await interaction.response.send_message("❌ This user is not currently muted/timed out!", ephemeral=True)
                return

            try:
                # Remove timeout by setting it to None
                await user.timeout(None, reason=reason)
                embed = discord.Embed(
                    title="🔊 User Unmuted",
                    description=f"Successfully unmuted {user.mention}",
                    color=discord.Color.green()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Unmuted By", value=interaction.user.mention, inline=True)

                # Send DM notification to the unmuted user
                try:
                    dm_embed = discord.Embed(
                        title="🔊 You were unmuted",
                        description=f"You were unmuted in **{interaction.guild.name}**",
                        color=discord.Color.green()
                    )
                    dm_embed.add_field(name="Reason", value=reason, inline=False)
                    dm_embed.add_field(name="Unmuted By", value=interaction.user.mention, inline=True)
                    await user.send(embed=dm_embed)
                    embed.add_field(name="DM Sent", value="✅", inline=True)
                except discord.Forbidden:
                    embed.add_field(name="DM Sent", value="❌ (DMs disabled)", inline=True)

                # Log the unmute in moderation audit
                if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                    self.moderation_cog.logger.create_moderation_audit_log(
                        interaction.guild.id, 'unmute', user.id, interaction.user.id,
                        details={'reason': reason}
                    )

            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Unmute Failed",
                    description="I don't have permission to unmute this user",
                    color=discord.Color.red()
                )
            except discord.HTTPException as e:
                embed = discord.Embed(
                    title="❌ Unmute Failed",
                    description=f"Failed to communicate with Discord: {e}",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error unmuting user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while unmuting the user",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ban", description="Ban a user from the server")
    @admin_only_interaction()
    async def ban_user(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        """Ban a user from the server"""
        try:
            # Check permissions
            if not interaction.guild.me.guild_permissions.ban_members:
                await interaction.response.send_message("❌ I don't have permission to ban members!", ephemeral=True)
                return

            # Prevent self-banning
            if user.id == interaction.user.id:
                await interaction.response.send_message("❌ You cannot ban yourself!", ephemeral=True)
                return

            # Prevent banning bots
            if user.bot:
                await interaction.response.send_message("❌ You cannot ban bots!", ephemeral=True)
                return

            try:
                await user.ban(reason=reason)
                embed = discord.Embed(
                    title="🔨 User Banned",
                    description=f"Successfully banned {user.mention}",
                    color=discord.Color.dark_red()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Banned By", value=interaction.user.mention, inline=True)

                # Send DM notification to the banned user
                try:
                    dm_embed = discord.Embed(
                        title="🔨 You were banned",
                        description=f"You were banned from **{interaction.guild.name}**",
                        color=discord.Color.dark_red()
                    )
                    dm_embed.add_field(name="Reason", value=reason, inline=False)
                    dm_embed.add_field(name="Banned By", value=interaction.user.mention, inline=True)
                    await user.send(embed=dm_embed)
                    embed.add_field(name="DM Sent", value="✅", inline=True)
                except discord.Forbidden:
                    embed.add_field(name="DM Sent", value="❌ (DMs disabled)", inline=True)

                # Log the ban in moderation audit
                if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                    self.moderation_cog.logger.create_moderation_audit_log(
                        interaction.guild.id, 'ban', user.id, interaction.user.id,
                        details={'reason': reason}
                    )

            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Ban Failed",
                    description="I don't have permission to ban this user",
                    color=discord.Color.red()
                )
            except discord.HTTPException as e:
                embed = discord.Embed(
                    title="❌ Ban Failed",
                    description=f"Failed to communicate with Discord: {e}",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error banning user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while banning the user",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="moderation_stats", description="View moderation statistics")
    @moderator_only_interaction()
    async def moderation_stats(self, interaction: discord.Interaction):
        """View moderation statistics for the server"""
        try:
            if not self.moderation_cog:
                await interaction.response.send_message("Moderation system not available", ephemeral=True)
                return

            # Get audit logs for this guild
            logs = self.moderation_cog.logger.get_audit_logs(interaction.guild.id, limit=1000)

            # Calculate statistics
            total_actions = len(logs)
            actions_by_type = {}
            recent_actions = [log for log in logs if self._is_recent(log['timestamp'])]

            for log in logs:
                action = log['action']
                actions_by_type[action] = actions_by_type.get(action, 0) + 1

            embed = discord.Embed(
                title="📊 Moderation Statistics",
                description=f"Server: {interaction.guild.name}",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Total Actions",
                value=str(total_actions),
                inline=True
            )

            embed.add_field(
                name="Recent Actions (24h)",
                value=str(len(recent_actions)),
                inline=True
            )

            # Most common actions
            if actions_by_type:
                top_actions = sorted(actions_by_type.items(), key=lambda x: x[1], reverse=True)[:5]
                actions_text = "\n".join(f"• {action.title()}: {count}" for action, count in top_actions)
                embed.add_field(name="Action Breakdown", value=actions_text, inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error getting moderation stats: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while retrieving statistics",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="moderation_logs", description="View recent moderation logs")
    @moderator_only_interaction()
    async def moderation_logs(self, interaction: discord.Interaction, page: int = 1):
        """View recent moderation action logs"""
        try:
            if not self.moderation_cog:
                await interaction.response.send_message("Moderation system not available", ephemeral=True)
                return

            logs = self.moderation_cog.logger.get_audit_logs(interaction.guild.id, limit=50)

            if not logs:
                embed = discord.Embed(
                    title="📝 Moderation Logs",
                    description="No moderation actions recorded yet",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Paginate (10 per page)
            per_page = 10
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page

            page_logs = logs[start_idx:end_idx]
            total_pages = (len(logs) - 1) // per_page + 1

            embed = discord.Embed(
                title="📝 Moderation Logs",
                description=f"Page {page}/{total_pages} • Total: {len(logs)} actions",
                color=discord.Color.blue()
            )

            for log in page_logs:
                # Format timestamp
                timestamp = self._format_timestamp(log['timestamp'])

                # Create log entry
                user_mention = f"<@{log['user_id']}>"
                moderator_mention = f"<@{log['moderator_id']}>"

                log_text = f"**{log['action'].title()}** - {user_mention} by {moderator_mention}\n"
                log_text += f"*{timestamp}*"

                if log.get('details', {}).get('reason'):
                    log_text += f" - {log['details']['reason']}"

                embed.add_field(
                    name=f"Action #{log['id'].split('_')[-1]}",
                    value=log_text,
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error getting moderation logs: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while retrieving logs",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    def _is_recent(self, timestamp_str: str, hours: int = 24) -> bool:
        """Check if timestamp is within the last N hours"""
        from datetime import datetime, timedelta
        try:
            log_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return datetime.now(log_time.tzinfo) - log_time < timedelta(hours=hours)
        except:
            return False

    def _format_timestamp(self, timestamp_str: str) -> str:
        """Format timestamp for display"""
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.strftime("%m/%d %H:%M")
        except:
            return timestamp_str

async def setup(bot):
    """Setup the moderation commands cog"""
    cog = ModerationCommands(bot)
    await bot.add_cog(cog)
    logger.info("Moderation commands cog loaded")
