import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Dict, List, Optional
from core.permissions import admin_only_interaction, moderator_only_interaction
from core.moderation.protection_manager import ProtectionManager
from core.moderation.scanner import MessageScanner
from core.moderation.enforcer import ProtectionEnforcer
from core.moderation.actions import ModerationActions
from core.moderation.scheduler import ModerationScheduler
from core.moderation.logger import ModerationLogger
from core.moderation.health import ModerationHealthChecker

logger = logging.getLogger(__name__)

class Moderation(commands.Cog):
    """Discord moderation system with profanity and link protection"""

    def __init__(self, bot):
        self.bot = bot
        self.data_manager = None  # Will be set by set_managers

        # Initialize moderation components with None data_manager initially
        self.protection_manager = ProtectionManager(None)
        self.scanner = MessageScanner(self.protection_manager)
        self.enforcer = ProtectionEnforcer(self.protection_manager, self.scanner, bot)
        self.actions = ModerationActions(self.protection_manager, bot)
        self.scheduler = ModerationScheduler(bot)
        self.logger = ModerationLogger(self.protection_manager, bot)
        self.health_checker = ModerationHealthChecker(
            self.protection_manager, self.scheduler, self.logger
        )

        logger.info("Moderation cog initialized")

    def set_managers(self, data_manager):
        """Set data manager reference"""
        self.data_manager = data_manager
        self.protection_manager.data_manager = data_manager

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Primary message listener hook that coordinates scanning, exemption checks, evaluation, and applying protection actions"""
        if message.author.bot or not message.guild:
            return

        config = self.protection_manager.load_protection_config(message.guild.id)
        if not config.get('enabled', True):
            return

        if self.protection_manager.is_exempt_from_protection(
            message.guild.id, message.author.id, message.channel.id, message.author.roles
        ):
            return

        try:
            profanity_matches = self.scanner.scan_message_for_profanity(message.guild.id, message.content)
            is_link_exempt = self.protection_manager.is_exempt_from_link_protection(message.guild.id, message.author)
            is_file_exempt = self.protection_manager.is_exempt_from_file_protection(message.guild.id, message.author)

            link_violations = []
            file_violations = []

            if not is_link_exempt:
                link_violations = self.scanner.scan_message_for_links(message.guild.id, message.content)
                embed_violations = self.scanner.scan_attachments_and_embeds(message.guild.id, message)
                link_violations += [v for v in embed_violations if v['type'] in ['embed_url', 'embed_description']]

            if not is_file_exempt:
                if message.attachments:
                    for attachment in message.attachments:
                        file_violations.append({'type': 'file_violation', 'filename': attachment.filename, 'url': attachment.url, 'reason': 'unauthorized_attachment'})
                if message.embeds:
                    for embed in message.embeds:
                        if embed.type in ['image', 'video', 'gifv']:
                            file_violations.append({'type': 'file_violation', 'url': embed.url, 'reason': 'unauthorized_media_embed'})

            if not profanity_matches and not link_violations and not file_violations:
                return

            action_plan = self.enforcer.evaluate_protection_action(message.guild.id, message, profanity_matches, link_violations, file_violations)
            result = await self.enforcer.apply_protection_action(action_plan, message)

            if result['success'] and result['action_taken'] != 'ignore':
                self.logger.create_moderation_audit_log(
                    message.guild.id, result['action_taken'], message.author.id, self.bot.user.id, message.id,
                    {'reason': result['reason'], 'severity': action_plan.get('severity', 'low'), 'profanity_matches': len(profanity_matches), 'link_violations': len(link_violations), 'file_violations': len(file_violations)}
                )
        except Exception as e:
            logger.error(f"Error in message moderation: {e}")

    @app_commands.command(name="add_profanity", description="Add a word to the profanity blacklist")
    @admin_only_interaction()
    async def command_add_profanity(self, interaction: discord.Interaction, word: str):
        """Slash command for admins to add profanity entries"""
        try:
            success, word_list = self.protection_manager.add_profanity_word(interaction.guild.id, word, interaction.user.id)
            if success:
                embed = discord.Embed(title="✅ Profanity Word Added", description=f"Added '{word}' to the profanity blacklist", color=discord.Color.green())
                embed.add_field(name="Total Words", value=str(len(word_list)), inline=True)
            else:
                embed = discord.Embed(title="❌ Error", description="Failed to add profanity word", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error adding profanity word: {e}")
            await interaction.response.send_message("An error occurred", ephemeral=True)

    @app_commands.command(name="remove_profanity", description="Remove a word from the profanity blacklist")
    @admin_only_interaction()
    async def command_remove_profanity(self, interaction: discord.Interaction, word: str):
        """Slash command for admins to remove profanity entries"""
        try:
            success, word_list = self.protection_manager.remove_profanity_word(interaction.guild.id, word, interaction.user.id)
            if success:
                embed = discord.Embed(title="✅ Profanity Word Removed", description=f"Removed '{word}' from the profanity blacklist", color=discord.Color.green())
                embed.add_field(name="Total Words", value=str(len(word_list)), inline=True)
            else:
                embed = discord.Embed(title="❌ Error", description=f"Word '{word}' not found", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error removing profanity word: {e}")
            await interaction.response.send_message("An error occurred", ephemeral=True)

    @app_commands.command(name="list_profanity", description="List current profanity blacklist")
    @admin_only_interaction()
    async def command_list_profanity(self, interaction: discord.Interaction, page: int = 1):
        """Admin command to view current blacklist"""
        try:
            word_list = self.protection_manager.get_profanity_list(interaction.guild.id)
            if not word_list:
                await interaction.response.send_message("No profanity words configured", ephemeral=True)
                return
            per_page = 20
            start = (page - 1) * per_page
            end = start + per_page
            page_words = word_list[start:end]
            total_pages = (len(word_list) - 1) // per_page + 1
            embed = discord.Embed(title="📝 Profanity Blacklist", description=f"Page {page}/{total_pages} • Total: {len(word_list)} words", color=discord.Color.blue())
            embed.add_field(name="Words", value="\n".join(f"• {w}" for w in page_words), inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error listing profanity: {e}")
            await interaction.response.send_message("An error occurred", ephemeral=True)

    @app_commands.command(name="add_whitelist", description="Add a domain to the link whitelist")
    @admin_only_interaction()
    async def command_add_whitelist(self, interaction: discord.Interaction, domain_or_regex: str):
        """Slash command to add a whitelisted domain"""
        try:
            success = self.protection_manager.add_whitelist_domain(interaction.guild.id, domain_or_regex, interaction.user.id)
            if success:
                await interaction.response.send_message(f"✅ Added '{domain_or_regex}' to whitelist", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to add to whitelist", ephemeral=True)
        except Exception as e:
            logger.error(f"Error adding whitelist: {e}")
            await interaction.response.send_message("An error occurred", ephemeral=True)

    @app_commands.command(name="remove_whitelist", description="Remove a domain from the link whitelist")
    @admin_only_interaction()
    async def command_remove_whitelist(self, interaction: discord.Interaction, domain_or_regex: str):
        """Slash command to remove whitelisted domain"""
        try:
            success = self.protection_manager.remove_whitelist_domain(interaction.guild.id, domain_or_regex, interaction.user.id)
            if success:
                await interaction.response.send_message(f"✅ Removed '{domain_or_regex}' from whitelist", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Domain not found", ephemeral=True)
        except Exception as e:
            logger.error(f"Error removing whitelist: {e}")
            await interaction.response.send_message("An error occurred", ephemeral=True)

    @app_commands.command(name="set_protection_level", description="Set protection strictness level")
    @admin_only_interaction()
    @app_commands.choices(level=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Monitor", value="monitor"),
        app_commands.Choice(name="Moderate", value="moderate"),
        app_commands.Choice(name="Strict", value="strict")
    ])
    async def command_set_protection_level(self, interaction: discord.Interaction, level: str):
        """Admin command to set protection strictness"""
        try:
            config = self.protection_manager.load_protection_config(interaction.guild.id)
            config['profanity_level'] = level
            success = self.protection_manager.save_protection_config(interaction.guild.id, config)
            if success:
                await interaction.response.send_message(f"✅ Protection level set to: **{level.title()}**", ephemeral=True)
                try:
                    from backend import sse_manager
                    sse_manager.broadcast_event('moderation_config_update', {'guild_id': str(interaction.guild.id), 'config': config})
                except:
                    pass
            else:
                await interaction.response.send_message("❌ Failed to update level", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting level: {e}")
            await interaction.response.send_message("An error occurred", ephemeral=True)

    @app_commands.command(name="warn", description="Issue a warning to a user")
    @moderator_only_interaction()
    async def warn_user(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        """Manually warn a user"""
        try:
            result = await self.actions.warn_user(interaction.guild.id, user.id, reason, interaction.user.id, auto_generated=False)
            if result['success']:
                embed = discord.Embed(title="⚠️ User Warned", description=f"Successfully warned {user.mention}", color=discord.Color.orange())
                embed.add_field(name="Reason", value=reason, inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Warning failed: {result.get('error', 'Unknown error')}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error warning: {e}")
            await interaction.response.send_message("An error occurred", ephemeral=True)

    @app_commands.command(name="mute", description="Temporarily mute a user")
    @moderator_only_interaction()
    async def mute_user(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: str):
        """Temporarily mute a user for specified minutes"""
        try:
            result = await self.actions.apply_temporary_mute(interaction.guild.id, user.id, duration * 60, reason, interaction.user.id)
            if result['success']:
                embed = discord.Embed(title="🔇 User Muted", description=f"Successfully muted {user.mention} for {duration} minutes", color=discord.Color.yellow())
                embed.add_field(name="Reason", value=reason, inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Mute failed: {result.get('error', 'Unknown error')}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error muting: {e}")
            await interaction.response.send_message("An error occurred", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a user from the server")
    @moderator_only_interaction()
    async def kick_user(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        """Kick a user from the server"""
        try:
            if not interaction.guild.me.guild_permissions.kick_members:
                await interaction.response.send_message("❌ I don't have permission to kick!", ephemeral=True)
                return
            await user.kick(reason=reason)
            self.logger.create_moderation_audit_log(interaction.guild.id, 'kick', user.id, interaction.user.id, {'reason': reason})
            await interaction.response.send_message(f"👢 Kicked {user.mention}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error kicking: {e}")
            await interaction.response.send_message(f"Failed to kick: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a user from the server")
    @admin_only_interaction()
    async def ban_user(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        """Ban a user from the server"""
        try:
            if not interaction.guild.me.guild_permissions.ban_members:
                await interaction.response.send_message("❌ I don't have permission to ban!", ephemeral=True)
                return
            await user.ban(reason=reason)
            self.logger.create_moderation_audit_log(interaction.guild.id, 'ban', user.id, interaction.user.id, {'reason': reason})
            await interaction.response.send_message(f"🔨 Banned {user.mention}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error banning: {e}")
            await interaction.response.send_message(f"Failed to ban: {e}", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user from the server")
    @admin_only_interaction()
    async def unban_user(self, interaction: discord.Interaction, user_id: str, reason: str = "Moderator action"):
        """Unban a user from the server"""
        try:
            if not interaction.guild.me.guild_permissions.ban_members:
                await interaction.response.send_message("❌ I don't have permission to unban!", ephemeral=True)
                return
            uid = int(user_id.strip('<@!>'))
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=reason)
            self.logger.create_moderation_audit_log(interaction.guild.id, 'unban', uid, interaction.user.id, {'reason': reason})
            await interaction.response.send_message(f"🔓 Unbanned {user.name}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error unbanning: {e}")
            await interaction.response.send_message(f"Failed to unban: {e}", ephemeral=True)

    @app_commands.command(name="unmute", description="Remove timeout/mute from a user")
    @moderator_only_interaction()
    async def unmute_user(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Moderator action"):
        """Remove timeout/mute from a user"""
        try:
            if not interaction.guild.me.guild_permissions.moderate_members:
                await interaction.response.send_message("❌ I don't have permission!", ephemeral=True)
                return
            await user.timeout(None, reason=reason)
            self.logger.create_moderation_audit_log(interaction.guild.id, 'unmute', user.id, interaction.user.id, {'reason': reason})
            await interaction.response.send_message(f"🔊 Unmuted {user.mention}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error unmuting: {e}")
            await interaction.response.send_message(f"Failed to unmute: {e}", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a user for a specified duration")
    @moderator_only_interaction()
    async def timeout_user(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: str = "Moderator action"):
        """Timeout (mute) a user for specified minutes"""
        try:
            if not interaction.guild.me.guild_permissions.moderate_members:
                await interaction.response.send_message("❌ I don't have permission!", ephemeral=True)
                return
            import datetime
            timeout_until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
            await user.timeout(timeout_until, reason=reason)
            self.logger.create_moderation_audit_log(interaction.guild.id, 'timeout', user.id, interaction.user.id, {'reason': reason, 'duration_minutes': duration})
            await interaction.response.send_message(f"⏰ Timed out {user.mention} for {duration} minutes", ephemeral=True)
        except Exception as e:
            logger.error(f"Error timeout: {e}")
            await interaction.response.send_message(f"Failed to timeout: {e}", ephemeral=True)

    @app_commands.command(name="softban", description="Ban then immediately unban a user (clears messages)")
    @moderator_only_interaction()
    async def softban_user(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Softban - message cleanup"):
        """Softban a user"""
        try:
            if not interaction.guild.me.guild_permissions.ban_members:
                await interaction.response.send_message("❌ No permission!", ephemeral=True)
                return
            await user.ban(reason=f"Softban: {reason}", delete_message_days=7)
            await interaction.guild.unban(user, reason=f"Softban complete: {reason}")
            self.logger.create_moderation_audit_log(interaction.guild.id, 'softban', user.id, interaction.user.id, {'reason': reason})
            await interaction.response.send_message(f"💨 Softbanned {user.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="pardon", description="Remove active strikes/warnings from a user")
    @moderator_only_interaction()
    async def pardon_user(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Moderator pardon"):
        """Pardon a user"""
        try:
            result = await self.actions.pardon_user(interaction.guild.id, user.id, reason, interaction.user.id)
            if result['success']:
                await interaction.response.send_message(f"🛡️ Pardoned {user.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Pardon failed", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

    @app_commands.command(name="clear", description="Clear messages from a channel")
    @moderator_only_interaction()
    async def clear_messages(self, interaction: discord.Interaction, amount: int = 10, user: discord.Member = None):
        """Clear messages"""
        try:
            if not interaction.channel.permissions_for(interaction.guild.me).manage_messages:
                await interaction.response.send_message("❌ No permission!", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            if user:
                deleted = await interaction.channel.purge(limit=amount, check=lambda m: m.author.id == user.id, before=interaction.created_at)
            else:
                deleted = await interaction.channel.purge(limit=amount, before=interaction.created_at)
            await interaction.followup.send(f"Successfully cleared {len(deleted)} messages.", ephemeral=True)
            self.logger.create_moderation_audit_log(interaction.guild.id, 'clear', 0, interaction.user.id, {'amount': len(deleted), 'channel_id': str(interaction.channel.id)})
        except Exception as e:
            await interaction.followup.send("Failed to clear messages.", ephemeral=True)

    @app_commands.command(name="slowmode", description="Set slowmode delay for the current channel")
    @moderator_only_interaction()
    async def set_slowmode(self, interaction: discord.Interaction, delay_seconds: int):
        """Set slowmode"""
        try:
            if not interaction.channel.permissions_for(interaction.guild.me).manage_channels:
                await interaction.response.send_message("❌ No permission!", ephemeral=True)
                return
            await interaction.channel.edit(slowmode_delay=delay_seconds)
            await interaction.response.send_message(f"Slowmode set to {delay_seconds} seconds.", ephemeral=True)
            self.logger.create_moderation_audit_log(interaction.guild.id, 'slowmode', 0, interaction.user.id, {'delay_seconds': delay_seconds, 'channel_id': str(interaction.channel.id)})
        except Exception as e:
            await interaction.response.send_message("Failed to set slowmode.", ephemeral=True)

    @app_commands.command(name="lock", description="Lock the current channel")
    @moderator_only_interaction()
    async def lock_channel(self, interaction: discord.Interaction, reason: str = "Channel locked"):
        """Lock channel"""
        try:
            if not interaction.channel.permissions_for(interaction.guild.me).manage_channels:
                await interaction.response.send_message("❌ No permission!", ephemeral=True)
                return
            overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.response.send_message(f"Channel locked: {reason}", ephemeral=True)
            self.logger.create_moderation_audit_log(interaction.guild.id, 'lock', 0, interaction.user.id, {'reason': reason, 'channel_id': str(interaction.channel.id)})
        except Exception as e:
            await interaction.response.send_message("Failed to lock channel.", ephemeral=True)

    @app_commands.command(name="unlock", description="Unlock the current channel")
    @moderator_only_interaction()
    async def unlock_channel(self, interaction: discord.Interaction, reason: str = "Channel unlocked"):
        """Unlock channel"""
        try:
            if not interaction.channel.permissions_for(interaction.guild.me).manage_channels:
                await interaction.response.send_message("❌ No permission!", ephemeral=True)
                return
            overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = None
            await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.response.send_message(f"Channel unlocked: {reason}", ephemeral=True)
            self.logger.create_moderation_audit_log(interaction.guild.id, 'unlock', 0, interaction.user.id, {'reason': reason, 'channel_id': str(interaction.channel.id)})
        except Exception as e:
            await interaction.response.send_message("Failed to unlock channel.", ephemeral=True)

    @app_commands.command(name="warnings", description="View a user's warning history")
    @moderator_only_interaction()
    async def view_warnings(self, interaction: discord.Interaction, user: discord.Member):
        """View warnings"""
        try:
            warnings_data = self.actions.get_user_warnings(interaction.guild.id, user.id)
            if not warnings_data or not warnings_data.get('strikes'):
                await interaction.response.send_message(f"{user.mention} has no warnings.", ephemeral=True)
                return
            strikes = warnings_data['strikes']
            embed = discord.Embed(title=f"⚠️ Warnings for {user.display_name}", description=f"Total Strikes: {len(strikes)}", color=discord.Color.yellow())
            for i, strike in enumerate(strikes[-5:], 1):
                embed.add_field(name=f"Warning #{i}", value=f"**Reason:** {strike.get('reason', 'N/A')}\n**Date:** {strike.get('created_at', 'N/A')[:10]}", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("Failed to retrieve warnings.", ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a user")
    @moderator_only_interaction()
    async def clear_warnings(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Moderator action"):
        """Clear warnings"""
        try:
            result = await self.actions.clear_user_warnings(interaction.guild.id, user.id, reason, interaction.user.id)
            if result['success']:
                await interaction.response.send_message(f"Cleared warnings for {user.mention}.", ephemeral=True)
            else:
                await interaction.response.send_message("Failed to clear warnings.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("An error occurred.", ephemeral=True)

    @app_commands.command(name="moderation_logs", description="View recent moderation logs")
    @moderator_only_interaction()
    async def command_moderation_logs(self, interaction: discord.Interaction, amount: int = 10):
        """View logs"""
        try:
            logs = self.logger.get_audit_logs(interaction.guild.id, limit=amount)
            if not logs:
                await interaction.response.send_message("No logs found.", ephemeral=True)
                return
            embed = discord.Embed(title="📝 Recent Moderation Logs", color=discord.Color.blue())
            for log in logs:
                timestamp = log.get('timestamp', '')[:16].replace('T', ' ')
                embed.add_field(name=f"{log['action'].upper()} | {timestamp}", value=f"Target: <@{log['user_id']}>\nMod: <@{log['moderator_id']}>\nReason: {log.get('details', {}).get('reason', 'N/A')}", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("Failed to retrieve logs.", ephemeral=True)

    @app_commands.command(name="moderation_stats", description="View moderation statistics")
    @moderator_only_interaction()
    async def moderation_stats(self, interaction: discord.Interaction):
        """View stats"""
        try:
            logs = self.logger.get_audit_logs(interaction.guild.id, limit=1000)
            actions_by_type = {}
            for log in logs:
                action = log['action']
                actions_by_type[action] = actions_by_type.get(action, 0) + 1
            embed = discord.Embed(title="📊 Moderation Statistics", description=f"Server: {interaction.guild.name}", color=discord.Color.blue())
            embed.add_field(name="Total Actions", value=str(len(logs)), inline=True)
            if actions_by_type:
                top_actions = sorted(actions_by_type.items(), key=lambda x: x[1], reverse=True)[:5]
                embed.add_field(name="Action Breakdown", value="\n".join(f"• {a.title()}: {c}" for a, c in top_actions), inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("Failed to retrieve stats.", ephemeral=True)

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
    """Setup the moderation cog"""
    cog = Moderation(bot)
    await bot.add_cog(cog)
    logger.info("Moderation cog loaded")
