"""
Real-time Synchronization Manager for CMS-Discord Integration
Handles bidirectional synchronization between CMS and Discord with conflict resolution.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
import json

logger = logging.getLogger(__name__)

class SyncEventType(Enum):
    """Types of synchronization events"""
    CMS_TO_DISCORD = "cms_to_discord"
    DISCORD_TO_CMS = "discord_to_cms"
    BIDIRECTIONAL_SYNC = "bidirectional_sync"
    CONFLICT_RESOLUTION = "conflict_resolution"

class SyncEntity(Enum):
    """Entities that can be synchronized"""
    TASK = "task"
    SHOP_ITEM = "shop_item"
    ANNOUNCEMENT = "announcement"
    EMBED = "embed"
    USER_BALANCE = "user_balance"
    CONFIG = "config"
    ROLE = "role"
    CHANNEL = "channel"

class SyncConflictResolution(Enum):
    """Conflict resolution strategies"""
    CMS_WINS = "cms_wins"  # CMS changes take precedence
    DISCORD_WINS = "discord_wins"  # Discord changes take precedence
    MERGE = "merge"  # Attempt to merge changes
    MANUAL = "manual"  # Require manual resolution
    LAST_MODIFIED = "last_modified"  # Use most recent change

class SyncManager:
    """Manages real-time bidirectional synchronization"""

    def __init__(self, data_manager, audit_manager, sse_manager):
        self.data_manager = data_manager
        self.audit_manager = audit_manager
        self.sse_manager = sse_manager

        # Sync state tracking
        self.sync_state: Dict[str, Dict[str, Any]] = {}
        self.pending_changes: Dict[str, List[Dict[str, Any]]] = {}
        self.conflict_queue: List[Dict[str, Any]] = []

        # Configuration
        self.sync_interval = 30  # seconds
        self.max_conflicts_per_entity = 10
        self.auto_resolve_strategy = SyncConflictResolution.LAST_MODIFIED

        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {}

        # Sync locks to prevent concurrent operations
        self.sync_locks: Dict[str, asyncio.Lock] = {}

    def register_event_handler(self, event_type: str, handler: Callable):
        """Register an event handler for sync events"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        logger.info(f"Registered sync event handler for: {event_type}")

    async def trigger_event(self, event_type: str, data: Dict[str, Any]):
        """Trigger sync event handlers"""
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    await handler(data)
                except Exception as e:
                    logger.error(f"Error in sync event handler {event_type}: {e}")

    async def sync_entity(self, entity_type: SyncEntity, entity_id: str, guild_id: int,
                         source: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronize an entity with conflict detection and resolution"""
        sync_key = f"{guild_id}:{entity_type.value}:{entity_id}"

        # Acquire sync lock
        if sync_key not in self.sync_locks:
            self.sync_locks[sync_key] = asyncio.Lock()

        async with self.sync_locks[sync_key]:
            try:
                # Check for existing sync state
                current_state = self._get_entity_state(entity_type, entity_id, guild_id)

                # Detect conflicts
                conflict = self._detect_conflict(current_state, changes, source)
                if conflict:
                    resolution = await self._resolve_conflict(conflict, entity_type, entity_id, guild_id)
                    if resolution['action'] == 'skip':
                        return {'success': False, 'reason': 'conflict_unresolved'}

                # Apply changes
                result = await self._apply_changes(entity_type, entity_id, guild_id, changes, source)

                # Update sync state
                self._update_sync_state(entity_type, entity_id, guild_id, changes, source)

                # Broadcast sync event
                await self._broadcast_sync_event(entity_type, entity_id, guild_id, source, changes)

                # Log audit event
                self.audit_manager.log_system_event(
                    'sync_completed',
                    guild_id,
                    {
                        'entity_type': entity_type.value,
                        'entity_id': entity_id,
                        'source': source,
                        'changes': changes
                    }
                )

                return {'success': True, 'result': result}

            except Exception as e:
                logger.error(f"Sync error for {sync_key}: {e}")
                return {'success': False, 'error': str(e)}

    async def sync_from_cms(self, entity_type: SyncEntity, entity_id: str, guild_id: int,
                           changes: Dict[str, Any]) -> Dict[str, Any]:
        """Sync changes from CMS to Discord"""
        return await self.sync_entity(entity_type, entity_id, guild_id, 'cms', changes)

    async def sync_from_discord(self, entity_type: SyncEntity, entity_id: str, guild_id: int,
                               changes: Dict[str, Any]) -> Dict[str, Any]:
        """Sync changes from Discord to CMS"""
        return await self.sync_entity(entity_type, entity_id, guild_id, 'discord', changes)

    async def bidirectional_sync(self, entity_type: SyncEntity, entity_id: str, guild_id: int) -> Dict[str, Any]:
        """Perform bidirectional synchronization"""
        try:
            # Get current state from both sources
            cms_state = self._get_cms_state(entity_type, entity_id, guild_id)
            discord_state = await self._get_discord_state(entity_type, entity_id, guild_id)

            # Compare states and determine sync actions
            sync_actions = self._compare_states(cms_state, discord_state, entity_type, entity_id, guild_id)

            results = []
            for action in sync_actions:
                if action['direction'] == 'cms_to_discord':
                    result = await self.sync_from_cms(entity_type, entity_id, guild_id, action['changes'])
                elif action['direction'] == 'discord_to_cms':
                    result = await self.sync_from_discord(entity_type, entity_id, guild_id, action['changes'])
                else:
                    continue

                results.append(result)

            return {
                'success': all(r['success'] for r in results),
                'actions_performed': len(results),
                'results': results
            }

        except Exception as e:
            logger.error(f"Bidirectional sync error for {entity_type.value}:{entity_id}: {e}")
            return {'success': False, 'error': str(e)}

    def _detect_conflict(self, current_state: Dict[str, Any], new_changes: Dict[str, Any],
                        source: str) -> Optional[Dict[str, Any]]:
        """Detect conflicts between current state and new changes"""
        if not current_state:
            return None  # No conflict if no current state

        conflicts = []

        # Check for conflicting field changes
        for field, new_value in new_changes.items():
            if field in current_state:
                current_value = current_state[field]
                last_modified = current_state.get('last_modified')
                source_of_truth = current_state.get('source')

                # Simple conflict detection: different values and different sources
                if current_value != new_value and source_of_truth != source:
                    # Check if change is recent (within conflict window)
                    if last_modified:
                        conflict_window = datetime.now(timezone.utc) - timedelta(minutes=5)
                        last_mod_time = datetime.fromisoformat(last_modified)

                        if last_mod_time > conflict_window:
                            conflicts.append({
                                'field': field,
                                'current_value': current_value,
                                'new_value': new_value,
                                'current_source': source_of_truth,
                                'new_source': source,
                                'last_modified': last_modified
                            })

        return {
            'entity_id': current_state.get('id'),
            'conflicts': conflicts,
            'current_state': current_state,
            'new_changes': new_changes
        } if conflicts else None

    async def _resolve_conflict(self, conflict: Dict[str, Any], entity_type: SyncEntity,
                               entity_id: str, guild_id: int) -> Dict[str, Any]:
        """Resolve synchronization conflicts"""
        try:
            # Auto-resolve based on strategy
            if self.auto_resolve_strategy == SyncConflictResolution.LAST_MODIFIED:
                # Use the most recent change
                current_time = datetime.fromisoformat(conflict['current_state']['last_modified'])
                new_time = datetime.now(timezone.utc)

                if new_time > current_time:
                    return {'action': 'apply_new', 'reason': 'newer_change'}
                else:
                    return {'action': 'keep_current', 'reason': 'existing_newer'}

            elif self.auto_resolve_strategy == SyncConflictResolution.CMS_WINS:
                return {'action': 'apply_new', 'reason': 'cms_priority'}

            elif self.auto_resolve_strategy == SyncConflictResolution.DISCORD_WINS:
                return {'action': 'keep_current', 'reason': 'discord_priority'}

            elif self.auto_resolve_strategy == SyncConflictResolution.MERGE:
                # Attempt to merge changes
                merged = self._merge_changes(conflict['current_state'], conflict['new_changes'])
                if merged:
                    return {'action': 'apply_merged', 'merged_changes': merged, 'reason': 'merged'}
                else:
                    return {'action': 'skip', 'reason': 'merge_failed'}

            else:
                # Manual resolution required
                self.conflict_queue.append({
                    'conflict': conflict,
                    'entity_type': entity_type,
                    'entity_id': entity_id,
                    'guild_id': guild_id,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

                # Broadcast conflict event
                await self._broadcast_sync_event(
                    entity_type, entity_id, guild_id, 'conflict',
                    {'conflict': conflict, 'requires_resolution': True}
                )

                return {'action': 'skip', 'reason': 'manual_resolution_required'}

        except Exception as e:
            logger.error(f"Conflict resolution error: {e}")
            return {'action': 'skip', 'reason': 'resolution_error'}

    def _merge_changes(self, current_state: Dict[str, Any], new_changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Attempt to merge conflicting changes"""
        try:
            merged = current_state.copy()

            # Simple merge strategy: prefer non-empty values
            for field, new_value in new_changes.items():
                current_value = current_state.get(field)

                # If current is empty and new is not, use new
                if not current_value and new_value:
                    merged[field] = new_value
                # If both have values and they're different, can't merge
                elif current_value and new_value and current_value != new_value:
                    return None  # Conflict can't be merged

            return merged

        except Exception as e:
            logger.error(f"Change merge error: {e}")
            return None

    async def _apply_changes(self, entity_type: SyncEntity, entity_id: str, guild_id: int,
                           changes: Dict[str, Any], source: str) -> Dict[str, Any]:
        """Apply changes to the appropriate system"""
        try:
            if source == 'cms':
                # Apply CMS changes to Discord
                return await self._apply_to_discord(entity_type, entity_id, guild_id, changes)
            else:
                # Apply Discord changes to CMS
                return await self._apply_to_cms(entity_type, entity_id, guild_id, changes)

        except Exception as e:
            logger.error(f"Error applying changes: {e}")
            raise

    async def _apply_to_discord(self, entity_type: SyncEntity, entity_id: str, guild_id: int,
                               changes: Dict[str, Any]) -> Dict[str, Any]:
        """Apply changes from CMS to Discord"""
        try:
            bot = self.data_manager.bot_instance
            if not bot:
                raise Exception("Bot instance not available")

            guild = bot.get_guild(guild_id)
            if not guild:
                raise Exception(f"Guild {guild_id} not found")

            if entity_type == SyncEntity.TASK:
                return await self._sync_task_to_discord(guild, entity_id, changes)
            elif entity_type == SyncEntity.SHOP_ITEM:
                return await self._sync_shop_item_to_discord(guild, entity_id, changes)
            elif entity_type == SyncEntity.ANNOUNCEMENT:
                return await self._sync_announcement_to_discord(guild, entity_id, changes)
            elif entity_type == SyncEntity.EMBED:
                return await self._sync_embed_to_discord(guild, entity_id, changes)
            else:
                logger.warning(f"Unsupported entity type for Discord sync: {entity_type}")
                return {'success': False, 'reason': 'unsupported_entity'}

        except Exception as e:
            logger.error(f"Error applying to Discord: {e}")
            return {'success': False, 'error': str(e)}

    async def _apply_to_cms(self, entity_type: SyncEntity, entity_id: str, guild_id: int,
                           changes: Dict[str, Any]) -> Dict[str, Any]:
        """Apply changes from Discord to CMS"""
        try:
            if entity_type == SyncEntity.USER_BALANCE:
                return await self._sync_balance_to_cms(guild_id, entity_id, changes)
            elif entity_type == SyncEntity.ROLE:
                return await self._sync_role_to_cms(guild_id, entity_id, changes)
            elif entity_type == SyncEntity.CHANNEL:
                return await self._sync_channel_to_cms(guild_id, entity_id, changes)
            else:
                # For other entities, update the database directly
                return self._update_cms_entity(entity_type, entity_id, guild_id, changes)

        except Exception as e:
            logger.error(f"Error applying to CMS: {e}")
            return {'success': False, 'error': str(e)}

    async def _sync_task_to_discord(self, guild, task_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Sync task changes to Discord message"""
        try:
            config = self.data_manager.load_guild_data(guild.id, 'config')
            task_channel_id = config.get('task_channel_id')

            if not task_channel_id:
                return {'success': False, 'reason': 'no_task_channel'}

            channel = guild.get_channel(int(task_channel_id))
            if not channel:
                return {'success': False, 'reason': 'channel_not_found'}

            # Get task data
            tasks_data = self.data_manager.load_guild_data(guild.id, 'tasks')
            task = tasks_data.get('tasks', {}).get(task_id)

            if not task:
                return {'success': False, 'reason': 'task_not_found'}

            # Update Discord message
            message_id = task.get('message_id')
            if message_id:
                try:
                    message = await channel.fetch_message(int(message_id))
                    embed = self._create_task_embed(task)
                    await message.edit(embed=embed)
                    return {'success': True, 'action': 'updated'}
                except:
                    # Message not found, create new one
                    pass

            # Create new message
            embed = self._create_task_embed(task)
            message = await channel.send(embed=embed)
            task['message_id'] = str(message.id)

            # Update database
            self.data_manager.save_guild_data(guild.id, 'tasks', tasks_data)

            return {'success': True, 'action': 'created', 'message_id': str(message.id)}

        except Exception as e:
            logger.error(f"Error syncing task to Discord: {e}")
            return {'success': False, 'error': str(e)}

    async def _sync_shop_item_to_discord(self, guild, item_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Sync shop item changes to Discord message"""
        try:
            config = self.data_manager.load_guild_data(guild.id, 'config')
            shop_channel_id = config.get('shop_channel_id')

            if not shop_channel_id:
                return {'success': False, 'reason': 'no_shop_channel'}

            channel = guild.get_channel(int(shop_channel_id))
            if not channel:
                return {'success': False, 'reason': 'channel_not_found'}

            # Get shop data
            currency_data = self.data_manager.load_guild_data(guild.id, 'currency')
            item = currency_data.get('shop_items', {}).get(item_id)

            if not item:
                return {'success': False, 'reason': 'item_not_found'}

            # Update Discord message
            message_id = item.get('message_id')
            if message_id:
                try:
                    message = await channel.fetch_message(int(message_id))
                    embed = self._create_shop_embed(item, config)
                    await message.edit(embed=embed)
                    return {'success': True, 'action': 'updated'}
                except:
                    # Message not found, create new one
                    pass

            # Create new message
            embed = self._create_shop_embed(item, config)
            message = await channel.send(embed=embed)
            item['message_id'] = str(message.id)

            # Update database
            self.data_manager.save_guild_data(guild.id, 'currency', currency_data)

            return {'success': True, 'action': 'created', 'message_id': str(message.id)}

        except Exception as e:
            logger.error(f"Error syncing shop item to Discord: {e}")
            return {'success': False, 'error': str(e)}

    async def _sync_announcement_to_discord(self, guild, announcement_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Sync announcement changes to Discord message"""
        try:
            # Get announcement data
            announcements_data = self.data_manager.load_guild_data(guild.id, 'announcements')
            announcement = announcements_data.get('announcements', {}).get(announcement_id)

            if not announcement:
                return {'success': False, 'reason': 'announcement_not_found'}

            channel_id = announcement.get('channel_id')
            if not channel_id:
                return {'success': False, 'reason': 'no_channel_id'}

            channel = guild.get_channel(int(channel_id))
            if not channel:
                return {'success': False, 'reason': 'channel_not_found'}

            # Update Discord message
            message_id = announcement.get('message_id')
            if message_id:
                try:
                    message = await channel.fetch_message(int(message_id))
                    # Update message content/embed
                    content = announcement.get('content', '')
                    embed_data = announcement.get('embed_data')

                    embed = None
                    if embed_data:
                        from core.embed_builder import EmbedBuilder
                        embed = EmbedBuilder.build_embed(embed_data)

                    await message.edit(content=content, embed=embed)
                    return {'success': True, 'action': 'updated'}
                except:
                    # Message not found
                    pass

            # Create new message
            content = announcement.get('content', '')
            embed = None
            if announcement.get('embed_data'):
                from core.embed_builder import EmbedBuilder
                embed = EmbedBuilder.build_embed(announcement['embed_data'])

            message = await channel.send(content=content, embed=embed)

            # Pin if requested
            if announcement.get('is_pinned'):
                try:
                    await message.pin()
                except:
                    pass  # Ignore pin errors

            announcement['message_id'] = str(message.id)

            # Update database
            self.data_manager.save_guild_data(guild.id, 'announcements', announcements_data)

            return {'success': True, 'action': 'created', 'message_id': str(message.id)}

        except Exception as e:
            logger.error(f"Error syncing announcement to Discord: {e}")
            return {'success': False, 'error': str(e)}

    async def _sync_embed_to_discord(self, guild, embed_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Sync embed changes to Discord message"""
        try:
            # Get embed data
            embeds_data = self.data_manager.load_guild_data(guild.id, 'embeds')
            embed_data = embeds_data.get('embeds', {}).get(embed_id)

            if not embed_data:
                return {'success': False, 'reason': 'embed_not_found'}

            channel_id = embed_data.get('channel_id')
            if not channel_id:
                return {'success': False, 'reason': 'no_channel_id'}

            channel = guild.get_channel(int(channel_id))
            if not channel:
                return {'success': False, 'reason': 'channel_not_found'}

            # Create embed
            from core.embed_builder import EmbedBuilder
            embed = EmbedBuilder.build_embed(embed_data)

            # Update Discord message
            message_id = embed_data.get('message_id')
            if message_id:
                try:
                    message = await channel.fetch_message(int(message_id))
                    await message.edit(embed=embed)
                    return {'success': True, 'action': 'updated'}
                except:
                    # Message not found, create new one
                    pass

            # Create new message
            message = await channel.send(embed=embed)
            embed_data['message_id'] = str(message.id)

            # Update database
            self.data_manager.save_guild_data(guild.id, 'embeds', embeds_data)

            return {'success': True, 'action': 'created', 'message_id': str(message.id)}

        except Exception as e:
            logger.error(f"Error syncing embed to Discord: {e}")
            return {'success': False, 'error': str(e)}

    async def _sync_balance_to_cms(self, guild_id: int, user_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Sync balance changes from Discord to CMS"""
        # This would be triggered by Discord events, but balance changes typically originate from CMS
        # This method handles cases where Discord events affect balances
        return {'success': True, 'action': 'balance_synced'}

    async def _sync_role_to_cms(self, guild_id: int, role_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Sync role changes from Discord to CMS"""
        try:
            # Update role information in database
            role_data = {
                'guild_id': str(guild_id),
                'role_id': role_id,
                'role_name': changes.get('name'),
                'role_color': changes.get('color'),
                'role_position': changes.get('position'),
                'permissions': changes.get('permissions', 0),
                'last_synced': datetime.now(timezone.utc).isoformat()
            }

            # Upsert role data
            self.data_manager.admin_client.table('guild_roles').upsert(role_data, on_conflict='guild_id,role_id').execute()

            return {'success': True, 'action': 'role_synced'}

        except Exception as e:
            logger.error(f"Error syncing role to CMS: {e}")
            return {'success': False, 'error': str(e)}

    async def _sync_channel_to_cms(self, guild_id: int, channel_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Sync channel changes from Discord to CMS"""
        # Channel changes are typically handled by the config system
        return {'success': True, 'action': 'channel_synced'}

    def _update_cms_entity(self, entity_type: SyncEntity, entity_id: str, guild_id: int,
                          changes: Dict[str, Any]) -> Dict[str, Any]:
        """Update entity in CMS database"""
        try:
            # This is a generic update method for entities that don't need special Discord sync
            data_type = self._get_data_type_for_entity(entity_type)
            if not data_type:
                return {'success': False, 'reason': 'unknown_entity_type'}

            # Load current data
            data = self.data_manager.load_guild_data(guild_id, data_type)

            # Apply changes
            if entity_type == SyncEntity.CONFIG:
                if 'config' not in data:
                    data['config'] = {}
                data['config'].update(changes)
            else:
                # For other entities, assume they're in a sub-dict
                container_key = self._get_container_key_for_entity(entity_type)
                if container_key not in data:
                    data[container_key] = {}
                if entity_id not in data[container_key]:
                    data[container_key][entity_id] = {}
                data[container_key][entity_id].update(changes)

            # Add last modified timestamp
            changes['last_modified'] = datetime.now(timezone.utc).isoformat()

            # Save data
            self.data_manager.save_guild_data(guild_id, data_type, data)

            return {'success': True, 'action': 'updated'}

        except Exception as e:
            logger.error(f"Error updating CMS entity: {e}")
            return {'success': False, 'error': str(e)}

    def _get_entity_state(self, entity_type: SyncEntity, entity_id: str, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get current sync state for an entity"""
        state_key = f"{guild_id}:{entity_type.value}:{entity_id}"
        return self.sync_state.get(state_key)

    def _update_sync_state(self, entity_type: SyncEntity, entity_id: str, guild_id: int,
                          changes: Dict[str, Any], source: str):
        """Update the sync state for an entity"""
        state_key = f"{guild_id}:{entity_type.value}:{entity_id}"

        if state_key not in self.sync_state:
            self.sync_state[state_key] = {}

        self.sync_state[state_key].update({
            'last_modified': datetime.now(timezone.utc).isoformat(),
            'source': source,
            'version': self.sync_state[state_key].get('version', 0) + 1,
            **changes
        })

    def _get_cms_state(self, entity_type: SyncEntity, entity_id: str, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get current state from CMS"""
        try:
            data_type = self._get_data_type_for_entity(entity_type)
            if not data_type:
                return None

            data = self.data_manager.load_guild_data(guild_id, data_type)
            container_key = self._get_container_key_for_entity(entity_type)

            if container_key and container_key in data:
                return data[container_key].get(entity_id)
            elif entity_type == SyncEntity.CONFIG:
                return data.get('config', {})

            return None

        except Exception as e:
            logger.error(f"Error getting CMS state: {e}")
            return None

    async def _get_discord_state(self, entity_type: SyncEntity, entity_id: str, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get current state from Discord"""
        try:
            bot = self.data_manager.bot_instance
            if not bot:
                return None

            guild = bot.get_guild(guild_id)
            if not guild:
                return None

            if entity_type == SyncEntity.ROLE:
                role = guild.get_role(int(entity_id))
                if role:
                    return {
                        'id': str(role.id),
                        'name': role.name,
                        'color': str(role.color),
                        'position': role.position,
                        'permissions': role.permissions.value
                    }
            elif entity_type == SyncEntity.CHANNEL:
                channel = guild.get_channel(int(entity_id))
                if channel:
                    return {
                        'id': str(channel.id),
                        'name': channel.name,
                        'type': str(channel.type),
                        'position': channel.position
                    }

            return None

        except Exception as e:
            logger.error(f"Error getting Discord state: {e}")
            return None

    def _compare_states(self, cms_state: Dict[str, Any], discord_state: Dict[str, Any],
                       entity_type: SyncEntity, entity_id: str, guild_id: int) -> List[Dict[str, Any]]:
        """Compare CMS and Discord states to determine sync actions"""
        actions = []

        if not cms_state and not discord_state:
            return actions

        # If one side is missing, sync from the other side
        if not cms_state and discord_state:
            actions.append({
                'direction': 'discord_to_cms',
                'changes': discord_state
            })
        elif cms_state and not discord_state:
            actions.append({
                'direction': 'cms_to_discord',
                'changes': cms_state
            })
        else:
            # Both exist, check for differences
            cms_time = datetime.fromisoformat(cms_state.get('last_modified', '2000-01-01T00:00:00'))
            discord_time = datetime.fromisoformat(discord_state.get('last_modified', '2000-01-01T00:00:00'))

            if cms_time > discord_time:
                actions.append({
                    'direction': 'cms_to_discord',
                    'changes': cms_state
                })
            elif discord_time > cms_time:
                actions.append({
                    'direction': 'discord_to_cms',
                    'changes': discord_state
                })

        return actions

    async def _broadcast_sync_event(self, entity_type: SyncEntity, entity_id: str, guild_id: int,
                                   source: str, changes: Dict[str, Any]):
        """Broadcast sync event via SSE"""
        try:
            event_data = {
                'guild_id': str(guild_id),
                'entity_type': entity_type.value,
                'entity_id': entity_id,
                'source': source,
                'changes': changes,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            self.sse_manager.broadcast_event('sync_update', event_data)

            # Trigger registered event handlers
            await self.trigger_event('sync_completed', event_data)

        except Exception as e:
            logger.error(f"Error broadcasting sync event: {e}")

    def _get_data_type_for_entity(self, entity_type: SyncEntity) -> Optional[str]:
        """Get the data type string for an entity type"""
        mapping = {
            SyncEntity.TASK: 'tasks',
            SyncEntity.SHOP_ITEM: 'currency',
            SyncEntity.ANNOUNCEMENT: 'announcements',
            SyncEntity.EMBED: 'embeds',
            SyncEntity.CONFIG: 'config',
            SyncEntity.USER_BALANCE: 'currency'
        }
        return mapping.get(entity_type)

    def _get_container_key_for_entity(self, entity_type: SyncEntity) -> Optional[str]:
        """Get the container key for an entity type"""
        mapping = {
            SyncEntity.TASK: 'tasks',
            SyncEntity.SHOP_ITEM: 'shop_items',
            SyncEntity.ANNOUNCEMENT: 'announcements',
            SyncEntity.EMBED: 'embeds',
            SyncEntity.USER_BALANCE: 'users'
        }
        return mapping.get(entity_type)

    def _create_task_embed(self, task: Dict[str, Any]) -> Any:
        """Create a Discord embed for a task"""
        import discord
        embed = discord.Embed(
            title=f"📋 {task['name']}",
            description=task.get('description', 'No description'),
            color=discord.Color.blue()
        )

        embed.add_field(name="Reward", value=f"💰 {task['reward']} coins", inline=True)
        embed.add_field(name="Status", value=task.get('status', 'active').title(), inline=True)

        if task.get('expires_at'):
            expires = datetime.fromisoformat(task['expires_at'])
            embed.add_field(name="Expires", value=f"<t:{int(expires.timestamp())}:R>", inline=True)

        embed.set_footer(text=f"Task ID: {task['id']}")

        return embed

    def _create_shop_embed(self, item: Dict[str, Any], config: Dict[str, Any]) -> Any:
        """Create a Discord embed for a shop item"""
        import discord
        currency_symbol = config.get('currency_symbol', '$')

        embed = discord.Embed(
            title=f"{item.get('emoji', '🛍️')} {item['name']}",
            description=item.get('description', 'No description'),
            color=discord.Color.green() if item.get('is_active', True) else discord.Color.grey()
        )

        embed.add_field(name="Price", value=f"{currency_symbol}{item['price']}", inline=True)

        stock = item.get('stock', -1)
        stock_text = "♾️ Unlimited" if stock == -1 else f"📦 {stock} available"
        embed.add_field(name="Stock", value=stock_text, inline=True)

        embed.set_footer(text="Use /buy <item_id> to purchase")

        return embed

    def get_sync_stats(self) -> Dict[str, Any]:
        """Get synchronization statistics"""
        return {
            'active_syncs': len(self.sync_state),
            'pending_changes': sum(len(changes) for changes in self.pending_changes.values()),
            'conflicts_queued': len(self.conflict_queue),
            'sync_locks': len(self.sync_locks)
        }

    def cleanup_old_sync_state(self, max_age_hours: int = 24):
        """Clean up old sync state entries"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        removed_count = 0

        keys_to_remove = []
        for key, state in self.sync_state.items():
            last_modified = state.get('last_modified')
            if last_modified:
                mod_time = datetime.fromisoformat(last_modified)
                if mod_time < cutoff_time:
                    keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.sync_state[key]
            removed_count += 1

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old sync state entries")

        return removed_count
