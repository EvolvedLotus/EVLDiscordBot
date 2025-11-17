import logging
from datetime import datetime
from typing import Dict, List
import discord

logger = logging.getLogger(__name__)

class ModerationLogger:
    """Handles logging and auditing of moderation actions"""

    def __init__(self, protection_manager, bot):
        self.protection_manager = protection_manager
        self.bot = bot
        self._audit_log = []  # In-memory audit log - would use database in production

    def create_moderation_audit_log(self, guild_id: int, action: str, user_id: int, moderator_id: int,
                                   message_id: int = None, details: Dict = None) -> Dict:
        """Records moderation actions with unique IDs for audits and undo capability"""
        audit_entry = {
            'id': f"audit_{guild_id}_{int(datetime.now().timestamp() * 1000)}",
            'guild_id': guild_id,
            'action': action,
            'user_id': user_id,
            'moderator_id': moderator_id,
            'message_id': message_id,
            'details': details or {},
            'timestamp': datetime.now().isoformat(),
            'can_undo': self._can_undo_action(action)
        }

        # Store in memory (would be database in production)
        self._audit_log.append(audit_entry)

        # Keep only last 1000 entries to prevent memory issues
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-1000:]

        # Log to configured channel
        self._log_to_channel(guild_id, audit_entry)

        logger.info(f"Moderation audit log created: {audit_entry}")
        return audit_entry

    def _can_undo_action(self, action: str) -> bool:
        """Determines if an action can be undone"""
        undoable_actions = ['mute', 'kick', 'ban', 'delete', 'warn']
        return action in undoable_actions

    async def _log_to_channel(self, guild_id: int, audit_entry: Dict):
        """Logs moderation action to configured channel"""
        try:
            config = self.protection_manager.load_protection_config(guild_id)
            log_channel_id = config.get('log_channel')

            if not log_channel_id:
                return

            guild = self.bot.get_guild(guild_id)
            if not guild:
                return

            channel = guild.get_channel(int(log_channel_id))
            if not channel:
                return

            # Create embed for log
            embed = discord.Embed(
                title=f"🛡️ Moderation Action: {audit_entry['action'].title()}",
                color=self._get_action_color(audit_entry['action']),
                timestamp=datetime.fromisoformat(audit_entry['timestamp'])
            )

            embed.add_field(
                name="User",
                value=f"<@{audit_entry['user_id']}>",
                inline=True
            )

            embed.add_field(
                name="Moderator",
                value=f"<@{audit_entry['moderator_id']}>",
                inline=True
            )

            if audit_entry.get('message_id'):
                embed.add_field(
                    name="Message ID",
                    value=f"`{audit_entry['message_id']}`",
                    inline=True
                )

            details = audit_entry.get('details', {})
            if details:
                detail_text = "\n".join([f"**{k}:** {v}" for k, v in details.items() if v])
                if len(detail_text) > 1000:
                    detail_text = detail_text[:997] + "..."
                embed.add_field(name="Details", value=detail_text, inline=False)

            embed.set_footer(text=f"Action ID: {audit_entry['id']}")

            await channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Failed to log moderation action to channel: {e}")

    def _get_action_color(self, action: str) -> discord.Color:
        """Returns appropriate color for action type"""
        colors = {
            'warn': discord.Color.orange(),
            'mute': discord.Color.yellow(),
            'kick': discord.Color.red(),
            'ban': discord.Color.dark_red(),
            'delete': discord.Color.blue(),
            'unmute': discord.Color.green(),
            'unban': discord.Color.green()
        }
        return colors.get(action, discord.Color.default())

    def get_audit_logs(self, guild_id: int, user_id: int = None, action: str = None,
                      limit: int = 50) -> List[Dict]:
        """Retrieves audit logs with optional filtering"""
        logs = [log for log in self._audit_log if log['guild_id'] == guild_id]

        if user_id:
            logs = [log for log in logs if log['user_id'] == user_id]

        if action:
            logs = [log for log in logs if log['action'] == action]

        # Sort by timestamp descending
        logs.sort(key=lambda x: x['timestamp'], reverse=True)

        return logs[:limit]

    def get_audit_log_by_id(self, audit_id: str) -> Dict:
        """Retrieves a specific audit log entry"""
        for log in self._audit_log:
            if log['id'] == audit_id:
                return log
        return None

    def export_moderation_logs(self, guild_id: int, start_date: datetime = None,
                              end_date: datetime = None, format: str = 'json') -> str:
        """Exports moderation/audit logs for compliance or review"""
        logs = [log for log in self._audit_log if log['guild_id'] == guild_id]

        # Filter by date range
        if start_date or end_date:
            filtered_logs = []
            for log in logs:
                log_date = datetime.fromisoformat(log['timestamp'])
                if start_date and log_date < start_date:
                    continue
                if end_date and log_date > end_date:
                    continue
                filtered_logs.append(log)
            logs = filtered_logs

        if format == 'json':
            import json
            return json.dumps(logs, indent=2, ensure_ascii=False)
        elif format == 'csv':
            import csv
            from io import StringIO
            output = StringIO()
            if logs:
                writer = csv.DictWriter(output, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)
            return output.getvalue()
        else:
            return "Unsupported format"
