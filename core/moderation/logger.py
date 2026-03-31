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
        """Records moderation actions with unique IDs for audits and undo capability in Postgres"""
        import uuid
        from datetime import timezone
        
        audit_id = f"audit_{guild_id}_{int(datetime.now().timestamp() * 1000)}"
        audit_entry = {
            'action_id': audit_id,
            'guild_id': str(guild_id),
            'user_id': str(user_id),
            'action_type': action,
            'moderator_id': str(moderator_id),
            'reason': (details or {}).get('reason', f"Auto action: {action}"),
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        # Store in Supabase
        try:
            dm = self.protection_manager.data_manager
            dm.supabase.table('moderation_actions').insert(audit_entry).execute()
        except Exception as e:
            logger.error(f"Failed to record audit log to DB: {e}")

        # Also recreate the legacy dict structure for _log_to_channel parsing
        legacy_entry = {
            'id': audit_id,
            'guild_id': guild_id,
            'action': action,
            'user_id': user_id,
            'moderator_id': moderator_id,
            'message_id': message_id,
            'details': details or {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Log to configured channel
        import asyncio
        if self.bot and self.bot.loop:
            asyncio.create_task(self._log_to_channel(guild_id, legacy_entry))

        logger.info(f"Moderation audit log created: {legacy_entry}")
        return legacy_entry

    def _can_undo_action(self, action: str) -> bool:
        """Determines if an action can be undone"""
        undoable_actions = ['mute', 'kick', 'ban', 'delete', 'warn']
        return action in undoable_actions

    async def _log_to_channel(self, guild_id: int, audit_entry: Dict):
        """Logs moderation action to configured channel"""
        try:
            config = self.protection_manager.load_protection_config(guild_id)
            log_channel_id = config.get('log_channel_id')

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
        """Retrieves audit logs natively from PostgREST with optional filtering"""
        try:
            query = self.protection_manager.data_manager.supabase.table('moderation_actions') \
                .select('*') \
                .eq('guild_id', str(guild_id)) \
                .order('created_at', desc=True) \
                .limit(limit)

            if user_id:
                query = query.eq('user_id', str(user_id))
            if action:
                query = query.eq('action_type', action)

            res = query.execute()
            if not res.data:
                return []
                
            # Maps postgres names back to discord log expectations
            logs = []
            for r in res.data:
                logs.append({
                    'id': r.get('action_id'),
                    'guild_id': int(r.get('guild_id')),
                    'action': r.get('action_type'),
                    'user_id': int(r.get('user_id')),
                    'moderator_id': int(r.get('moderator_id')),
                    'details': {'reason': r.get('reason')},
                    'timestamp': r.get('created_at')
                })
            return logs
        except Exception as e:
            logger.error(f"Failed to fetch audit logs: {e}")
            return []

    def get_audit_log_by_id(self, audit_id: str) -> Dict:
        """Retrieves a specific native audit log entry"""
        try:
            res = self.protection_manager.data_manager.supabase.table('moderation_actions') \
                .select('*').eq('action_id', audit_id).execute()
            return res.data[0] if res.data else None
        except:
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
