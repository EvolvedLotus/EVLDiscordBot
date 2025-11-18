import logging
import discord
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from .protection_manager import ProtectionManager
from .scanner import MessageScanner

logger = logging.getLogger(__name__)

class ProtectionEnforcer:
    """Executes protection actions based on scan results"""

    def __init__(self, protection_manager: ProtectionManager, scanner: MessageScanner, bot):
        self.protection_manager = protection_manager
        self.scanner = scanner
        self.bot = bot

    def evaluate_protection_action(self, guild_id: int, message: discord.Message, matches: List[Dict], links: List[Dict]) -> Dict:
        """Decides action based on guild protection config and severity"""
        config = self.protection_manager.load_protection_config(guild_id)

        if not config.get('enabled', True):
            return {'action': 'ignore', 'reason': 'protection_disabled'}

        # Determine highest severity
        max_severity = 'low'
        if matches:
            severities = [match['severity'] for match in matches]
            if 'high' in severities:
                max_severity = 'high'
            elif 'medium' in severities:
                max_severity = 'medium'

        # Check for unauthorized links
        unauthorized_links = [link for link in links if link['is_blacklisted'] and not link['is_whitelisted']]

        # Decide action based on config and severity
        action_plan = {
            'action': 'ignore',
            'reason': 'no_violation',
            'severity': max_severity,
            'notify': False
        }

        # Profanity actions
        if matches and config.get('profanity_filter', True):
            auto_actions = config.get('auto_actions', {})

            if max_severity == 'high' and auto_actions.get('ban', False):
                action_plan.update({
                    'action': 'ban',
                    'reason': 'high_severity_profanity',
                    'notify': True
                })
            elif max_severity == 'high' and auto_actions.get('kick', False):
                action_plan.update({
                    'action': 'kick',
                    'reason': 'high_severity_profanity',
                    'notify': True
                })
            elif max_severity == 'high' and auto_actions.get('mute', False):
                action_plan.update({
                    'action': 'mute',
                    'reason': 'high_severity_profanity',
                    'notify': True
                })
            elif auto_actions.get('warn', True):
                action_plan.update({
                    'action': 'warn',
                    'reason': 'profanity_detected',
                    'notify': True
                })
            else:
                action_plan.update({
                    'action': 'delete',
                    'reason': 'profanity_detected',
                    'notify': False
                })

        # Link violation actions (override profanity if more severe)
        if unauthorized_links:
            action_plan.update({
                'action': 'delete',
                'reason': 'unauthorized_link',
                'severity': 'medium',
                'notify': True
            })

        return action_plan

    async def apply_protection_action(self, action_plan: Dict, message: discord.Message, moderator_context: str = None) -> Dict:
        """Executes the decided action"""
        try:
            action = action_plan['action']
            reason = action_plan['reason']

            result = {
                'success': True,
                'action_taken': action,
                'reason': reason,
                'details': {}
            }

            if action == 'ignore':
                return result

            # Delete message
            if action in ['delete', 'warn', 'mute', 'kick', 'ban']:
                try:
                    await message.delete()
                    result['details']['message_deleted'] = True
                except discord.Forbidden:
                    logger.warning(f"Cannot delete message in {message.guild.name}")
                    result['details']['message_deleted'] = False

            # Apply user actions
            if action == 'warn':
                await self._warn_user(message, reason)
                result['details']['user_warned'] = True

            elif action == 'mute':
                await self._apply_temporary_mute(message, reason)
                result['details']['user_muted'] = True

            elif action == 'kick':
                await self._kick_user(message, reason)
                result['details']['user_kicked'] = True

            elif action == 'ban':
                await self._ban_user(message, reason)
                result['details']['user_banned'] = True

            # Log the action
            await self._create_moderation_audit_log(message, action_plan, result)

            # Send notification if required
            if action_plan.get('notify', False):
                await self._send_notification(message, action_plan)

            return result

        except Exception as e:
            logger.error(f"Failed to apply protection action: {e}")
            return {
                'success': False,
                'error': str(e),
                'action_taken': 'error'
            }

    def redact_message_content(self, message: discord.Message, match_ranges: List[Tuple[int, int]]) -> Optional[str]:
        """Replaces offensive substrings with safe placeholder"""
        if not message.content:
            return None

        content = message.content
        # Sort ranges in reverse order to avoid offset issues
        match_ranges.sort(key=lambda x: x[0], reverse=True)

        for start, end in match_ranges:
            if start < len(content) and end <= len(content):
                # Replace with █ characters
                replacement = '█' * (end - start)
                content = content[:start] + replacement + content[end:]

        return content

    async def quarantine_message(self, message: discord.Message, reason: str) -> Dict:
        """Moves message content to moderator-only storage"""
        # For now, just log it - full quarantine system would need a database table
        quarantine_record = {
            'message_id': message.id,
            'channel_id': message.channel.id,
            'guild_id': message.guild.id,
            'author_id': message.author.id,
            'content': message.content,
            'attachments': [att.url for att in message.attachments],
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }

        logger.info(f"Quarantined message: {quarantine_record}")

        # Try to delete original message
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        return quarantine_record

    async def _warn_user(self, message: discord.Message, reason: str):
        """Issues a warning to user via DM"""
        try:
            embed = discord.Embed(
                title="⚠️ Warning",
                description=f"You received a warning in **{message.guild.name}**",
                color=discord.Color.orange()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.set_footer(text="Repeated violations may result in further action")

            await message.author.send(embed=embed)
        except discord.Forbidden:
            # Cannot DM user
            pass

    async def _apply_temporary_mute(self, message: discord.Message, reason: str):
        """Applies temporary mute via timeout"""
        try:
            # Apply 10 minute timeout
            duration = timedelta(minutes=10)
            await message.author.timeout(duration, reason=reason)

            # Schedule unmute (would need a scheduler system)
            # For now, just log it
            logger.info(f"Muted user {message.author.id} for 10 minutes in guild {message.guild.id}")

        except discord.Forbidden:
            logger.warning(f"Cannot mute user {message.author.id} in guild {message.guild.id}")

    async def _kick_user(self, message: discord.Message, reason: str):
        """Kicks user from guild"""
        try:
            await message.author.kick(reason=reason)
            logger.info(f"Kicked user {message.author.id} from guild {message.guild.id}")
        except discord.Forbidden:
            logger.warning(f"Cannot kick user {message.author.id} in guild {message.guild.id}")

    async def _ban_user(self, message: discord.Message, reason: str):
        """Bans user from guild"""
        try:
            await message.author.ban(reason=reason)
            logger.info(f"Banned user {message.author.id} from guild {message.guild.id}")
        except discord.Forbidden:
            logger.warning(f"Cannot ban user {message.author.id} in guild {message.guild.id}")

    async def _create_moderation_audit_log(self, message: discord.Message, action_plan: Dict, result: Dict):
        """Records moderation actions for audit"""
        audit_log = {
            'guild_id': message.guild.id,
            'action': action_plan['action'],
            'user_id': message.author.id,
            'moderator_id': self.bot.user.id,  # Automated action
            'message_id': message.id,
            'channel_id': message.channel.id,
            'reason': action_plan['reason'],
            'severity': action_plan.get('severity', 'low'),
            'details': result.get('details', {}),
            'timestamp': datetime.now().isoformat()
        }

        # Log to configured channel if available
        config = self.protection_manager.load_protection_config(message.guild.id)
        log_channel_id = config.get('log_channel')

        if log_channel_id:
            try:
                log_channel = message.guild.get_channel(int(log_channel_id))
                if log_channel:
                    embed = discord.Embed(
                        title=f"🛡️ Moderation Action: {action_plan['action'].title()}",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="User", value=message.author.mention, inline=True)
                    embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                    embed.add_field(name="Reason", value=action_plan['reason'], inline=True)
                    embed.add_field(name="Severity", value=action_plan.get('severity', 'low'), inline=True)

                    if message.content:
                        # Truncate long messages
                        content = message.content[:500] + "..." if len(message.content) > 500 else message.content
                        embed.add_field(name="Message Content", value=f"```{content}```", inline=False)

                    await log_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to send moderation log: {e}")

        logger.info(f"Moderation action logged: {audit_log}")

    async def _send_notification(self, message: discord.Message, action_plan: Dict):
        """Sends notification to moderators"""
        # Try to send to the channel where violation occurred
        try:
            embed = discord.Embed(
                title="🛡️ Message Removed",
                description=f"A message by {message.author.mention} was removed for: **{action_plan['reason']}**",
                color=discord.Color.red()
            )
            embed.set_footer(text="This message will auto-delete in 30 seconds")

            notification = await message.channel.send(embed=embed)

            # Auto-delete after 30 seconds
            import asyncio
            await asyncio.sleep(30)
            try:
                await notification.delete()
            except:
                pass

        except discord.Forbidden:
            # Cannot send in channel
            pass
