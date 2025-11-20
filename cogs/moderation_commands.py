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



    @app_commands.command(name="timeout", description="Timeout a user for a specified duration")
    @moderator_only_interaction()
    async def timeout_user(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: str = "Moderator action"):
        """Timeout (mute) a user for specified minutes"""
        try:
            # Check permissions
            if not interaction.guild.me.guild_permissions.moderate_members:
                await interaction.response.send_message("❌ I don't have permission to moderate members!", ephemeral=True)
                return

            # Prevent self-timeout
            if user.id == interaction.user.id:
                await interaction.response.send_message("❌ You cannot timeout yourself!", ephemeral=True)
                return

            # Prevent timeout bots (unless necessary)
            if user.bot:
                await interaction.response.send_message("❌ You cannot timeout bots!", ephemeral=True)
                return

            # Convert minutes to timedelta
            duration_seconds = duration * 60
            timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)

            try:
                # Apply timeout
                await user.timeout(timeout_until, reason=reason)
                embed = discord.Embed(
                    title="⏰ User Timed Out",
                    description=f"Successfully timed out {user.mention} for {duration} minutes",
                    color=discord.Color.yellow()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Duration", value=f"{duration} minutes", inline=True)
                embed.add_field(name="Timed Out By", value=interaction.user.mention, inline=True)

                # Send DM notification if possible
                try:
                    dm_embed = discord.Embed(
                        title="⏰ You were timed out",
                        description=f"You were timed out in **{interaction.guild.name}** for {duration} minutes",
                        color=discord.Color.yellow()
                    )
                    dm_embed.add_field(name="Reason", value=reason, inline=False)
                    dm_embed.add_field(name="Ends", value=f"<t:{int(timeout_until.timestamp())}:R>", inline=True)
                    await user.send(embed=dm_embed)
                    embed.add_field(name="DM Sent", value="✅", inline=True)
                except discord.Forbidden:
                    embed.add_field(name="DM Sent", value="❌ (DMs disabled)", inline=True)

                # Log the timeout in moderation audit
                if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                    self.moderation_cog.logger.create_moderation_audit_log(
                        interaction.guild.id, 'timeout', user.id, interaction.user.id,
                        details={'reason': reason, 'duration_minutes': duration}
                    )

            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Timeout Failed",
                    description="I don't have permission to timeout this user",
                    color=discord.Color.red()
                )
            except discord.HTTPException as e:
                embed = discord.Embed(
                    title="❌ Timeout Failed",
                    description=f"Failed to communicate with Discord: {e}",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error timing out user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while timing out the user",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user from the server")
    @moderator_only_interaction()
    async def unban_user(self, interaction: discord.Interaction, user_id: str, reason: str = "Moderator action"):
        """Unban a user from the server"""
        try:
            # Check permissions
            if not interaction.guild.me.guild_permissions.ban_members:
                await interaction.response.send_message("❌ I don't have permission to ban/unban members!", ephemeral=True)
                return

            try:
                # Convert user_id string to int
                user_id_int = int(user_id.strip('<@!>'))

                # Fetch the user
                user = await interaction.client.fetch_user(user_id_int)

                try:
                    # Attempt to unban
                    await interaction.guild.unban(user, reason=reason)
                    embed = discord.Embed(
                        title="🔓 User Unbanned",
                        description=f"Successfully unbanned {user.mention if user else f'User {user_id}'}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Reason", value=reason, inline=False)
                    embed.add_field(name="Unbanned By", value=interaction.user.mention, inline=True)

                    # Log the unban in moderation audit
                    if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                        self.moderation_cog.logger.create_moderation_audit_log(
                            interaction.guild.id, 'unban', user.id if user else user_id_int, interaction.user.id,
                            details={'reason': reason}
                        )

                except discord.NotFound:
                    embed = discord.Embed(
                        title="❌ Unban Failed",
                        description="This user is not banned or the ID is invalid",
                        color=discord.Color.red()
                    )
                except discord.Forbidden:
                    embed = discord.Embed(
                        title="❌ Unban Failed",
                        description="I don't have permission to unban this user",
                        color=discord.Color.red()
                    )

            except ValueError:
                embed = discord.Embed(
                    title="❌ Invalid User ID",
                    description="Please provide a valid user ID or mention",
                    color=discord.Color.red()
                )
            except discord.NotFound:
                embed = discord.Embed(
                    title="❌ User Not Found",
                    description="The user ID provided is invalid",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while unbanning the user",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="softban", description="Ban then immediately unban a user (clears messages)")
    @moderator_only_interaction()
    async def softban_user(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Softban - message cleanup"):
        """Softban a user (ban then immediate unban to clear messages)"""
        try:
            # Check permissions
            if not interaction.guild.me.guild_permissions.ban_members:
                await interaction.response.send_message("❌ I don't have permission to ban/unban members!", ephemeral=True)
                return

            # Prevent self-softban
            if user.id == interaction.user.id:
                await interaction.response.send_message("❌ You cannot softban yourself!", ephemeral=True)
                return

            # Prevent softban bots
            if user.bot:
                await interaction.response.send_message("❌ You cannot softban bots!", ephemeral=True)
                return

            try:
                # Softban: ban then immediately unban (clears up to 7 days of messages)
                await user.ban(reason=f"Softban: {reason}", delete_message_days=7)
                await interaction.guild.unban(user, reason=f"Softban complete: {reason}")

                embed = discord.Embed(
                    title="💨 User Softbanned",
                    description=f"Successfully softbanned {user.mention} - messages cleared",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Action", value="Banned then unbanned to clear messages", inline=False)
                embed.add_field(name="Messages Cleared", value="Up to 7 days", inline=True)
                embed.add_field(name="Softbanned By", value=interaction.user.mention, inline=True)

                # Send DM notification if possible
                try:
                    dm_embed = discord.Embed(
                        title="💨 You were softbanned",
                        description=f"You were softbanned from **{interaction.guild.name}**",
                        color=discord.Color.orange()
                    )
                    dm_embed.add_field(name="Reason", value=reason, inline=False)
                    dm_embed.add_field(name="Details", value="This removes you from the server temporarily to clear messages, but you can rejoin immediately.", inline=False)
                    await user.send(embed=dm_embed)
                    embed.add_field(name="DM Sent", value="✅", inline=True)
                except discord.Forbidden:
                    embed.add_field(name="DM Sent", value="❌ (DMs disabled)", inline=True)

                # Log the softban in moderation audit
                if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                    self.moderation_cog.logger.create_moderation_audit_log(
                        interaction.guild.id, 'softban', user.id, interaction.user.id,
                        details={'reason': reason}
                    )

            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Softban Failed",
                    description="I don't have permission to ban/unban this user",
                    color=discord.Color.red()
                )
            except discord.HTTPException as e:
                embed = discord.Embed(
                    title="❌ Softban Failed",
                    description=f"Failed to communicate with Discord: {e}",
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error softbanning user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while softbanning the user",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="pardon", description="Remove active strikes/warnings from a user")
    @moderator_only_interaction()
    async def pardon_user(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Moderator pardon"):
        """Pardon a user by removing their active strikes/warnings"""
        try:
            if not self.moderation_cog or not self.moderation_cog.actions:
                await interaction.response.send_message("Moderation system not available", ephemeral=True)
                return

            # Use the moderation actions to pardon
            result = await self.moderation_cog.actions.pardon_user(
                interaction.guild.id, user.id, reason, interaction.user.id
            )

            if result['success']:
                # Count pardoned strikes if available
                pardon_count = result.get('strikes_pardoned', 'some')
                embed = discord.Embed(
                    title="🛡️ User Pardoned",
                    description=f"Successfully pardoned {user.mention}",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Status", value="Active strikes cleared", inline=True)
                if isinstance(pardon_count, int):
                    embed.add_field(name="Strikes Pardoned", value=str(pardon_count), inline=True)
                embed.add_field(name="Pardoned By", value=interaction.user.mention, inline=True)

                # Send DM notification if possible
                try:
                    dm_embed = discord.Embed(
                        title="🛡️ You were pardoned",
                        description=f"You were pardoned in **{interaction.guild.name}**",
                        color=discord.Color.blue()
                    )
                    dm_embed.add_field(name="Reason", value=reason, inline=False)
                    dm_embed.add_field(name="Details", value="Your active strikes/warnings have been cleared.", inline=False)
                    await user.send(embed=dm_embed)
                    embed.add_field(name="DM Sent", value="✅", inline=True)
                except discord.Forbidden:
                    embed.add_field(name="DM Sent", value="❌ (DMs disabled)", inline=True)
            else:
                embed = discord.Embed(
                    title="❌ Pardon Failed",
                    description=result.get('error', 'Unknown error'),
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error pardoning user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while pardoning the user",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="warnings", description="View a user's warning history")
    @moderator_only_interaction()
    async def view_warnings(self, interaction: discord.Interaction, user: discord.Member):
        """View a user's warning/strike history"""
        try:
            if not self.moderation_cog:
                await interaction.response.send_message("Moderation system not available", ephemeral=True)
                return

            # Get user warnings/strikes
            warnings_data = self.moderation_cog.actions.get_user_warnings(interaction.guild.id, user.id)

            if not warnings_data or not warnings_data.get('strikes'):
                embed = discord.Embed(
                    title="📋 Warning History",
                    description=f"{user.mention} has no warnings or strikes",
                    color=discord.Color.green()
                )
            else:
                strikes = warnings_data['strikes']
                active_strikes = [s for s in strikes if s.get('is_active', True)]

                embed = discord.Embed(
                    title="⚠️ Warning History",
                    description=f"Warnings for {user.mention}",
                    color=discord.Color.yellow()
                )

                embed.add_field(name="Total Strikes", value=str(len(strikes)), inline=True)
                embed.add_field(name="Active Strikes", value=str(len(active_strikes)), inline=True)

                # List recent warnings
                for i, strike in enumerate(strikes[-10:], 1):  # Show last 10
                    timestamp = datetime.fromisoformat(strike['created_at'].replace('Z', '+00:00'))
                    is_active = strike.get('is_active', True)
                    status_icon = "⚠️" if is_active else "✅"

                    embed.add_field(
                        name=f"{status_icon} Warning #{len(strikes) - 10 + i}",
                        value=f"**Reason:** {strike.get('reason', 'Unknown')}\n"
                              f"**By:** <@{strike.get('moderator_id', 'Unknown')}>\n"
                              f"**Date:** <t:{int(timestamp.timestamp())}:F>\n"
                              f"**Status:** {'Active' if is_active else 'Resolved'}",
                        inline=False
                    )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error viewing warnings: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while retrieving warning history",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a user")
    @moderator_only_interaction()
    async def clear_warnings(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Moderator action"):
        """Clear all warnings/strikes for a user"""
        try:
            if not self.moderation_cog or not self.moderation_cog.actions:
                await interaction.response.send_message("Moderation system not available", ephemeral=True)
                return

            # Clear all warnings/strikes
            result = await self.moderation_cog.actions.clear_user_warnings(
                interaction.guild.id, user.id, reason, interaction.user.id
            )

            if result['success']:
                cleared_count = result.get('cleared_count', 0)
                embed = discord.Embed(
                    title="🧹 Warnings Cleared",
                    description=f"Successfully cleared warnings for {user.mention}",
                    color=discord.Color.green()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Warnings Cleared", value=str(cleared_count), inline=True)
                embed.add_field(name="Cleared By", value=interaction.user.mention, inline=True)

                # Send DM notification if possible
                try:
                    dm_embed = discord.Embed(
                        title="🧹 Warnings Cleared",
                        description=f"All your warnings have been cleared in **{interaction.guild.name}**",
                        color=discord.Color.green()
                    )
                    dm_embed.add_field(name="Reason", value=reason, inline=False)
                    await user.send(embed=dm_embed)
                    embed.add_field(name="DM Sent", value="✅", inline=True)
                except discord.Forbidden:
                    embed.add_field(name="DM Sent", value="❌ (DMs disabled)", inline=True)
            else:
                embed = discord.Embed(
                    title="❌ Clear Warnings Failed",
                    description=result.get('error', 'Unknown error'),
                    color=discord.Color.red()
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error clearing warnings: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while clearing warnings",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clear", description="Clear messages from a channel")
    @moderator_only_interaction()
    async def clear_messages(self, interaction: discord.Interaction, amount: int = 10, user: discord.Member = None):
        """Clear messages from the current channel (max 1000)"""
        try:
            # Check permissions
            if not interaction.channel.permissions_for(interaction.guild.me).manage_messages:
                await interaction.response.send_message("❌ I don't have permission to manage messages in this channel!", ephemeral=True)
                return

            # Validate amount
            if amount < 1:
                await interaction.response.send_message("❌ Must clear at least 1 message!", ephemeral=True)
                return
            if amount > 1000:
                await interaction.response.send_message("❌ Cannot clear more than 1000 messages at once!", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            # Clear messages
            if user:
                # Clear messages from specific user
                def check(message):
                    return message.author.id == user.id

                deleted = await interaction.channel.purge(limit=amount, check=check, before=interaction.created_at)
                target_desc = f" from {user.mention}"
            else:
                # Clear any messages
                deleted = await interaction.channel.purge(limit=amount, before=interaction.created_at)
                target_desc = ""

            embed = discord.Embed(
                title="🧹 Messages Cleared",
                description=f"Successfully cleared {len(deleted)} message(s){target_desc} in {interaction.channel.mention}",
                color=discord.Color.green()
            )
            embed.add_field(name="Requested Amount", value=str(amount), inline=True)
            embed.add_field(name="Actually Cleared", value=str(len(deleted)), inline=True)
            embed.add_field(name="Cleared By", value=interaction.user.mention, inline=True)

            # Log the clear action in moderation audit
            if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                self.moderation_cog.logger.create_moderation_audit_log(
                    interaction.guild.id, 'clear', 0, interaction.user.id,
                    details={'amount': amount, 'channel_id': str(interaction.channel.id), 'user_target_id': str(user.id) if user else None}
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error clearing messages: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while clearing messages",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="slowmode", description="Set slowmode delay for the current channel")
    @moderator_only_interaction()
    async def set_slowmode(self, interaction: discord.Interaction, delay_seconds: int):
        """Set slowmode delay in seconds for the current channel"""
        try:
            # Check permissions
            if not interaction.channel.permissions_for(interaction.guild.me).manage_channels:
                await interaction.response.send_message("❌ I don't have permission to manage this channel!", ephemeral=True)
                return

            # Validate delay (Discord limit is 21600 seconds = 6 hours)
            if delay_seconds < 0:
                await interaction.response.send_message("❌ Delay cannot be negative!", ephemeral=True)
                return
            if delay_seconds > 21600:
                await interaction.response.send_message("❌ Delay cannot exceed 21600 seconds (6 hours)!", ephemeral=True)
                return

            # Set slowmode
            await interaction.channel.edit(slowmode_delay=delay_seconds)

            if delay_seconds == 0:
                embed = discord.Embed(
                    title="🐌 Slowmode Disabled",
                    description=f"Slowmode has been disabled in {interaction.channel.mention}",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="🐌 Slowmode Set",
                    description=f"Slowmode set to {delay_seconds} seconds in {interaction.channel.mention}",
                    color=discord.Color.blue()
                )

            embed.add_field(name="Delay", value=f"{delay_seconds} seconds", inline=True)
            embed.add_field(name="Set By", value=interaction.user.mention, inline=True)

            # Log the slowmode action in moderation audit
            if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                self.moderation_cog.logger.create_moderation_audit_log(
                    interaction.guild.id, 'slowmode', 0, interaction.user.id,
                    details={'delay_seconds': delay_seconds, 'channel_id': str(interaction.channel.id)}
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error setting slowmode: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while setting slowmode",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="lock", description="Lock the current channel (prevent messaging)")
    @moderator_only_interaction()
    async def lock_channel(self, interaction: discord.Interaction, reason: str = "Channel locked by moderator"):
        """Lock the current channel by denying send_messages permission for @everyone"""
        try:
            # Check permissions
            if not interaction.channel.permissions_for(interaction.guild.me).manage_channels:
                await interaction.response.send_message("❌ I don't have permission to manage this channel!", ephemeral=True)
                return

            # Get current permissions for @everyone
            everyone_overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)

            # If already locked, inform user
            if everyone_overwrite.send_messages is False:
                await interaction.response.send_message("❌ This channel is already locked!", ephemeral=True)
                return

            # Lock the channel
            everyone_overwrite.send_messages = False
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=everyone_overwrite)

            embed = discord.Embed(
                title="🔒 Channel Locked",
                description=f"Successfully locked {interaction.channel.mention}",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Locked By", value=interaction.user.mention, inline=True)

            # Log the lock action in moderation audit
            if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                self.moderation_cog.logger.create_moderation_audit_log(
                    interaction.guild.id, 'lock', 0, interaction.user.id,
                    details={'reason': reason, 'channel_id': str(interaction.channel.id)}
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error locking channel: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while locking the channel",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unlock", description="Unlock the current channel (allow messaging)")
    @moderator_only_interaction()
    async def unlock_channel(self, interaction: discord.Interaction, reason: str = "Channel unlocked by moderator"):
        """Unlock the current channel by restoring send_messages permission for @everyone"""
        try:
            # Check permissions
            if not interaction.channel.permissions_for(interaction.guild.me).manage_channels:
                await interaction.response.send_message("❌ I don't have permission to manage this channel!", ephemeral=True)
                return

            # Get current permissions for @everyone
            everyone_overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)

            # If not locked, inform user
            if everyone_overwrite.send_messages is not False:
                await interaction.response.send_message("❌ This channel is not locked!", ephemeral=True)
                return

            # Unlock the channel
            everyone_overwrite.send_messages = None  # Remove the override
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=everyone_overwrite)

            embed = discord.Embed(
                title="🔓 Channel Unlocked",
                description=f"Successfully unlocked {interaction.channel.mention}",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Unlocked By", value=interaction.user.mention, inline=True)

            # Log the unlock action in moderation audit
            if self.moderation_cog and hasattr(self.moderation_cog, 'logger'):
                self.moderation_cog.logger.create_moderation_audit_log(
                    interaction.guild.id, 'unlock', 0, interaction.user.id,
                    details={'reason': reason, 'channel_id': str(interaction.channel.id)}
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error unlocking channel: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while unlocking the channel",
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
