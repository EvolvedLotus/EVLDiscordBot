"""
Comprehensive Audit Logging System for CMS-Discord Integration
Tracks all moderation actions, system events, and user activities with detailed logging.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class AuditEventType(Enum):
    """Audit event types"""
    # User actions
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_REGISTER = "user.register"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"

    # Moderation actions
    MODERATION_KICK = "moderation.kick"
    MODERATION_BAN = "moderation.ban"
    MODERATION_UNBAN = "moderation.unban"
    MODERATION_TIMEOUT = "moderation.timeout"
    MODERATION_UNTIMEOUT = "moderation.untimeout"
    MODERATION_WARN = "moderation.warn"
    MODERATION_STRIKE_ADD = "moderation.strike.add"
    MODERATION_STRIKE_REMOVE = "moderation.strike.remove"
    MODERATION_MESSAGE_DELETE = "moderation.message.delete"
    MODERATION_MESSAGE_EDIT = "moderation.message.edit"

    # Content management
    CONTENT_TASK_CREATE = "content.task.create"
    CONTENT_TASK_UPDATE = "content.task.update"
    CONTENT_TASK_DELETE = "content.task.delete"
    CONTENT_TASK_COMPLETE = "content.task.complete"
    CONTENT_SHOP_ITEM_CREATE = "content.shop.create"
    CONTENT_SHOP_ITEM_UPDATE = "content.shop.update"
    CONTENT_SHOP_ITEM_DELETE = "content.shop.delete"
    CONTENT_ANNOUNCEMENT_CREATE = "content.announcement.create"
    CONTENT_ANNOUNCEMENT_UPDATE = "content.announcement.update"
    CONTENT_ANNOUNCEMENT_DELETE = "content.announcement.delete"
    CONTENT_EMBED_CREATE = "content.embed.create"
    CONTENT_EMBED_UPDATE = "content.embed.update"
    CONTENT_EMBED_DELETE = "content.embed.delete"

    # Currency actions
    CURRENCY_GRANT = "currency.grant"
    CURRENCY_REVOKE = "currency.revoke"
    CURRENCY_TRANSFER = "currency.transfer"
    CURRENCY_PURCHASE = "currency.purchase"

    # System events
    SYSTEM_CONFIG_UPDATE = "system.config.update"
    SYSTEM_BACKUP = "system.backup"
    SYSTEM_RESTORE = "system.restore"
    SYSTEM_ERROR = "system.error"
    SYSTEM_MAINTENANCE = "system.maintenance"

    # Discord sync events
    DISCORD_ROLE_UPDATE = "discord.role.update"
    DISCORD_CHANNEL_UPDATE = "discord.channel.update"
    DISCORD_MEMBER_JOIN = "discord.member.join"

    DISCORD_MEMBER_LEAVE = "discord.member.leave"

    # CMS events
    CMS_ACTION = "cms.action"

class AuditManager:
    """Comprehensive audit logging system"""

    def __init__(self, data_manager):
        self.data_manager = data_manager
        self.audit_buffer: List[Dict[str, Any]] = []
        self.buffer_size = 50  # Batch size for database writes
        self.retention_days = 90  # Keep audit logs for 90 days

    def log_event(self, event_type: AuditEventType, guild_id: int, user_id: Optional[int],
                  moderator_id: Optional[int], details: Dict[str, Any],
                  message_id: Optional[str] = None, can_undo: bool = False) -> str:
        """Log an audit event"""
        try:
            audit_id = f"audit_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{guild_id}"

            audit_entry = {
                'audit_id': audit_id,
                'guild_id': str(guild_id),
                'event_type': event_type.value if hasattr(event_type, 'value') else str(event_type),
                'user_id': str(user_id) if user_id else None,
                'moderator_id': str(moderator_id) if moderator_id else None,
                'message_id': message_id,
                'details': json.dumps(details),
                'can_undo': can_undo,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'ip_address': None,  # Set by calling context
                'user_agent': None   # Set by calling context
            }

            # Add to buffer
            self.audit_buffer.append(audit_entry)

            # Flush if buffer is full
            if len(self.audit_buffer) >= self.buffer_size:
                self._flush_audit_buffer()

            event_type_str = event_type.value if hasattr(event_type, 'value') else str(event_type)
            logger.info(f"Audit event logged: {event_type_str} for guild {guild_id}")
            return audit_id

        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            return None

    def log_moderation_action(self, action_type: str, guild_id: int, user_id: int,
                             moderator_id: int, reason: str, details: Dict[str, Any] = None,
                             duration_seconds: int = None, message_id: str = None) -> str:
        """Log a moderation action with enhanced details"""
        try:
            # Map action type to audit event
            event_mapping = {
                'kick': AuditEventType.MODERATION_KICK,
                'ban': AuditEventType.MODERATION_BAN,
                'unban': AuditEventType.MODERATION_UNBAN,
                'timeout': AuditEventType.MODERATION_TIMEOUT,
                'untimeout': AuditEventType.MODERATION_UNTIMEOUT,
                'warn': AuditEventType.MODERATION_WARN,
                'strike_add': AuditEventType.MODERATION_STRIKE_ADD,
                'strike_remove': AuditEventType.MODERATION_STRIKE_REMOVE,
                'message_delete': AuditEventType.MODERATION_MESSAGE_DELETE,
                'message_edit': AuditEventType.MODERATION_MESSAGE_EDIT
            }

            event_type = event_mapping.get(action_type)
            if not event_type:
                logger.warning(f"Unknown moderation action type: {action_type}")
                event_type = AuditEventType.SYSTEM_ERROR

            # Build details
            action_details = {
                'reason': reason,
                'action_type': action_type,
                'duration_seconds': duration_seconds,
                **(details or {})
            }

            can_undo = action_type in ['ban', 'timeout', 'kick']  # Actions that can potentially be undone

            return self.log_event(
                event_type=event_type,
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=moderator_id,
                details=action_details,
                message_id=message_id,
                can_undo=can_undo
            )

        except Exception as e:
            logger.error(f"Failed to log moderation action: {e}")
            return None

    def log_content_action(self, action_type: str, guild_id: int, user_id: int,
                          content_type: str, content_id: str, details: Dict[str, Any] = None) -> str:
        """Log content management actions"""
        try:
            # Map content action to audit event
            event_mapping = {
                'create': {
                    'task': AuditEventType.CONTENT_TASK_CREATE,
                    'shop': AuditEventType.CONTENT_SHOP_ITEM_CREATE,
                    'announcement': AuditEventType.CONTENT_ANNOUNCEMENT_CREATE,
                    'embed': AuditEventType.CONTENT_EMBED_CREATE
                },
                'update': {
                    'task': AuditEventType.CONTENT_TASK_UPDATE,
                    'shop': AuditEventType.CONTENT_SHOP_ITEM_UPDATE,
                    'announcement': AuditEventType.CONTENT_ANNOUNCEMENT_UPDATE,
                    'embed': AuditEventType.CONTENT_EMBED_UPDATE
                },
                'delete': {
                    'task': AuditEventType.CONTENT_TASK_DELETE,
                    'shop': AuditEventType.CONTENT_SHOP_ITEM_DELETE,
                    'announcement': AuditEventType.CONTENT_ANNOUNCEMENT_DELETE,
                    'embed': AuditEventType.CONTENT_EMBED_DELETE
                },
                'complete': {
                    'task': AuditEventType.CONTENT_TASK_COMPLETE
                }
            }

            if action_type not in event_mapping or content_type not in event_mapping[action_type]:
                logger.warning(f"Unknown content action: {action_type} {content_type}")
                return None

            event_type = event_mapping[action_type][content_type]

            action_details = {
                'content_type': content_type,
                'content_id': content_id,
                'action': action_type,
                **(details or {})
            }

            return self.log_event(
                event_type=event_type,
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=user_id,  # Content actions are typically self-moderated
                details=action_details,
                can_undo=action_type == 'delete'
            )

        except Exception as e:
            logger.error(f"Failed to log content action: {e}")
            return None

    def log_currency_action(self, action_type: str, guild_id: int, user_id: int,
                           amount: int, reason: str, moderator_id: Optional[int] = None,
                           details: Dict[str, Any] = None) -> str:
        """Log currency-related actions"""
        try:
            event_mapping = {
                'grant': AuditEventType.CURRENCY_GRANT,
                'revoke': AuditEventType.CURRENCY_REVOKE,
                'transfer': AuditEventType.CURRENCY_TRANSFER,
                'purchase': AuditEventType.CURRENCY_PURCHASE
            }

            event_type = event_mapping.get(action_type)
            if not event_type:
                logger.warning(f"Unknown currency action type: {action_type}")
                return None

            action_details = {
                'amount': amount,
                'reason': reason,
                'action_type': action_type,
                **(details or {})
            }

            return self.log_event(
                event_type=event_type,
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=moderator_id or user_id,
                details=action_details,
                can_undo=action_type in ['grant', 'revoke']
            )

        except Exception as e:
            logger.error(f"Failed to log currency action: {e}")
            return None

    def log_system_event(self, event_type: str, guild_id: int, details: Dict[str, Any],
                        user_id: Optional[int] = None) -> str:
        """Log system-level events"""
        try:
            event_mapping = {
                'config_update': AuditEventType.SYSTEM_CONFIG_UPDATE,
                'backup': AuditEventType.SYSTEM_BACKUP,
                'restore': AuditEventType.SYSTEM_RESTORE,
                'error': AuditEventType.SYSTEM_ERROR,
                'maintenance': AuditEventType.SYSTEM_MAINTENANCE
            }

            audit_event_type = event_mapping.get(event_type)
            if not audit_event_type:
                logger.warning(f"Unknown system event type: {event_type}")
                return None

            return self.log_event(
                event_type=audit_event_type,
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=None,
                details={'event_type': event_type, **details}
            )

        except Exception as e:
            logger.error(f"Failed to log system event: {e}")
            return None

    def log_discord_event(self, event_type: str, guild_id: int, details: Dict[str, Any],
                         user_id: Optional[int] = None) -> str:
        """Log Discord-related events"""
        try:
            event_mapping = {
                'role_update': AuditEventType.DISCORD_ROLE_UPDATE,
                'channel_update': AuditEventType.DISCORD_CHANNEL_UPDATE,
                'member_join': AuditEventType.DISCORD_MEMBER_JOIN,
                'member_leave': AuditEventType.DISCORD_MEMBER_LEAVE
            }

            audit_event_type = event_mapping.get(event_type)
            if not audit_event_type:
                logger.warning(f"Unknown Discord event type: {event_type}")
                return None

            return self.log_event(
                event_type=audit_event_type,
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=None,
                details={'discord_event': event_type, **details}
            )

        except Exception as e:
            logger.error(f"Failed to log Discord event: {e}")
            return None

    def get_audit_logs(self, guild_id: int, filters: Dict[str, Any] = None,
                      limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Retrieve audit logs with filtering"""
        try:
            query = self.data_manager.admin_client.table('moderation_audit_logs').select('*')

            # Apply filters
            query = query.eq('guild_id', str(guild_id))

            if filters:
                if 'event_type' in filters:
                    query = query.eq('event_type', filters['event_type'])
                if 'user_id' in filters:
                    query = query.eq('user_id', str(filters['user_id']))
                if 'moderator_id' in filters:
                    query = query.eq('moderator_id', str(filters['moderator_id']))
                if 'start_date' in filters:
                    query = query.gte('created_at', filters['start_date'])
                if 'end_date' in filters:
                    query = query.lte('created_at', filters['end_date'])

            # Apply pagination and ordering
            result = query.order('created_at', desc=True).range(offset, offset + limit - 1).execute()

            logs = []
            for log in result.data:
                logs.append({
                    'audit_id': log['audit_id'],
                    'event_type': log['event_type'],
                    'user_id': log['user_id'],
                    'moderator_id': log['moderator_id'],
                    'message_id': log['message_id'],
                    'details': json.loads(log['details']) if log['details'] else {},
                    'can_undo': log['can_undo'],
                    'created_at': log['created_at']
                })

            # Get total count
            count_result = self.data_manager.admin_client.table('moderation_audit_logs').select('audit_id', count='exact').eq('guild_id', str(guild_id))
            if filters:
                if 'event_type' in filters:
                    count_result = count_result.eq('event_type', filters['event_type'])
                if 'user_id' in filters:
                    count_result = count_result.eq('user_id', str(filters['user_id']))
                if 'moderator_id' in filters:
                    count_result = count_result.eq('moderator_id', str(filters['moderator_id']))

            count_data = count_result.execute()
            total_count = count_data.count if hasattr(count_data, 'count') else len(logs)

            return {
                'logs': logs,
                'total_count': total_count,
                'limit': limit,
                'offset': offset
            }

        except Exception as e:
            logger.error(f"Failed to retrieve audit logs: {e}")
            return {'logs': [], 'total_count': 0, 'limit': limit, 'offset': offset}

    def undo_action(self, audit_id: str, moderator_id: int) -> bool:
        """Attempt to undo a logged action"""
        try:
            # Get the audit log entry
            result = self.data_manager.admin_client.table('moderation_audit_logs').select('*').eq('audit_id', audit_id).execute()

            if not result.data:
                logger.warning(f"Audit log entry not found: {audit_id}")
                return False

            log_entry = result.data[0]

            if not log_entry['can_undo']:
                logger.warning(f"Action cannot be undone: {audit_id}")
                return False

            # Parse details to determine undo action
            details = json.loads(log_entry['details']) if log_entry['details'] else {}

            # This would need specific logic for each undoable action type
            # For now, we'll mark the action as undone in the audit log
            self.data_manager.admin_client.table('moderation_audit_logs').update({
                'details': json.dumps({**details, 'undone': True, 'undone_by': str(moderator_id), 'undone_at': datetime.now(timezone.utc).isoformat()})
            }).eq('audit_id', audit_id).execute()

            logger.info(f"Action undone: {audit_id} by moderator {moderator_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to undo action {audit_id}: {e}")
            return False

    def get_audit_stats(self, guild_id: int, days: int = 30) -> Dict[str, Any]:
        """Get audit statistics for a guild"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            # Get event type counts
            result = self.data_manager.admin_client.table('moderation_audit_logs').select('event_type').eq('guild_id', str(guild_id)).gte('created_at', cutoff_date.isoformat()).execute()

            event_counts = {}
            for log in result.data:
                event_type = log['event_type']
                event_counts[event_type] = event_counts.get(event_type, 0) + 1

            # Get moderator activity
            mod_result = self.data_manager.admin_client.table('moderation_audit_logs').select('moderator_id, event_type').eq('guild_id', str(guild_id)).gte('created_at', cutoff_date.isoformat()).execute()

            moderator_activity = {}
            for log in mod_result.data:
                mod_id = log['moderator_id']
                if mod_id:
                    if mod_id not in moderator_activity:
                        moderator_activity[mod_id] = {}
                    event_type = log['event_type']
                    moderator_activity[mod_id][event_type] = moderator_activity[mod_id].get(event_type, 0) + 1

            return {
                'event_counts': event_counts,
                'moderator_activity': moderator_activity,
                'period_days': days,
                'total_events': len(result.data)
            }

        except Exception as e:
            logger.error(f"Failed to get audit stats: {e}")
            return {'event_counts': {}, 'moderator_activity': {}, 'period_days': days, 'total_events': 0}

    def cleanup_old_logs(self, days_to_keep: int = 90) -> int:
        """Clean up old audit logs beyond retention period"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

            # Delete old logs
            result = self.data_manager.admin_client.table('moderation_audit_logs').delete().lt('created_at', cutoff_date.isoformat()).execute()

            deleted_count = len(result.data) if result.data else 0
            logger.info(f"Cleaned up {deleted_count} old audit logs")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old audit logs: {e}")
            return 0

    def _flush_audit_buffer(self):
        """Flush buffered audit entries to database"""
        if not self.audit_buffer:
            return

        try:
            # Insert all buffered entries
            self.data_manager.admin_client.table('moderation_audit_logs').insert(self.audit_buffer).execute()

            logger.debug(f"Flushed {len(self.audit_buffer)} audit entries to database")
            self.audit_buffer.clear()

        except Exception as e:
            logger.error(f"Failed to flush audit buffer: {e}")
            # Keep buffer for retry on next flush

    def export_audit_logs(self, guild_id: int, filters: Dict[str, Any] = None,
                         format_type: str = 'json') -> Optional[str]:
        """Export audit logs in various formats"""
        try:
            logs_data = self.get_audit_logs(guild_id, filters, limit=10000)  # Large limit for export

            if format_type == 'json':
                return json.dumps(logs_data['logs'], indent=2)
            elif format_type == 'csv':
                import csv
                import io

                output = io.StringIO()
                if logs_data['logs']:
                    writer = csv.DictWriter(output, fieldnames=logs_data['logs'][0].keys())
                    writer.writeheader()
                    writer.writerows(logs_data['logs'])

                return output.getvalue()
            else:
                logger.warning(f"Unsupported export format: {format_type}")
                return None

        except Exception as e:
            logger.error(f"Failed to export audit logs: {e}")
            return None

    def __del__(self):
        """Ensure buffer is flushed on destruction"""
        if self.audit_buffer:
            self._flush_audit_buffer()
