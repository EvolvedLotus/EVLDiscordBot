"""
Comprehensive tests for the SyncManager bidirectional synchronization system
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
import json

from core.sync_manager import SyncManager, SyncEntity, SyncConflictResolution
from core.audit_manager import AuditManager
from core.data_manager import DataManager


class TestSyncManager:
    """Test suite for SyncManager"""

    @pytest.fixture
    def mock_data_manager(self):
        """Mock data manager for testing"""
        dm = Mock(spec=DataManager)
        dm.admin_client = Mock()
        dm.load_guild_data = Mock(return_value={'config': {}})
        dm.save_guild_data = Mock(return_value=True)
        dm.bot_instance = Mock()
        return dm

    @pytest.fixture
    def mock_audit_manager(self):
        """Mock audit manager for testing"""
        am = Mock(spec=AuditManager)
        am.log_system_event = Mock()
        return am

    @pytest.fixture
    def mock_sse_manager(self):
        """Mock SSE manager for testing"""
        sse = Mock()
        sse.broadcast_event = Mock()
        return sse

    @pytest.fixture
    def sync_manager(self, mock_data_manager, mock_audit_manager, mock_sse_manager):
        """Create SyncManager instance for testing"""
        return SyncManager(mock_data_manager, mock_audit_manager, mock_sse_manager)

    @pytest.mark.asyncio
    async def test_sync_entity_basic(self, sync_manager):
        """Test basic entity synchronization"""
        # Mock the apply_changes method
        sync_manager._apply_changes = AsyncMock(return_value={'success': True, 'result': 'applied'})

        result = await sync_manager.sync_entity(
            entity_type=SyncEntity.TASK,
            entity_id='task_123',
            guild_id=123456789,
            source='cms',
            changes={'name': 'Updated Task', 'status': 'active'}
        )

        assert result['success'] == True
        assert result['result'] == 'applied'

        # Verify audit logging
        sync_manager.audit_manager.log_system_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_from_cms(self, sync_manager):
        """Test synchronization from CMS to Discord"""
        sync_manager.sync_entity = AsyncMock(return_value={'success': True})

        result = await sync_manager.sync_from_cms(
            entity_type=SyncEntity.TASK,
            entity_id='task_123',
            guild_id=123456789,
            changes={'name': 'New Task'}
        )

        assert result['success'] == True
        sync_manager.sync_entity.assert_called_once_with(
            SyncEntity.TASK, 'task_123', 123456789, 'cms', {'name': 'New Task'}
        )

    @pytest.mark.asyncio
    async def test_sync_from_discord(self, sync_manager):
        """Test synchronization from Discord to CMS"""
        sync_manager.sync_entity = AsyncMock(return_value={'success': True})

        result = await sync_manager.sync_from_discord(
            entity_type=SyncEntity.USER_BALANCE,
            entity_id='user_456',
            guild_id=123456789,
            changes={'balance': 1500}
        )

        assert result['success'] == True
        sync_manager.sync_entity.assert_called_once_with(
            SyncEntity.USER_BALANCE, 'user_456', 123456789, 'discord', {'balance': 1500}
        )

    @pytest.mark.asyncio
    async def test_bidirectional_sync(self, sync_manager):
        """Test bidirectional synchronization"""
        # Mock state getters
        sync_manager._get_cms_state = Mock(return_value={'name': 'Task A', 'last_modified': '2025-01-01T10:00:00'})
        sync_manager._get_discord_state = AsyncMock(return_value={'name': 'Task A', 'last_modified': '2025-01-01T11:00:00'})

        # Mock sync actions
        sync_manager.sync_from_cms = AsyncMock(return_value={'success': True})
        sync_manager.sync_from_discord = AsyncMock(return_value={'success': True})

        result = await sync_manager.bidirectional_sync(
            entity_type=SyncEntity.TASK,
            entity_id='task_123',
            guild_id=123456789
        )

        assert result['success'] == True
        assert result['actions_performed'] == 1  # Discord state is newer

        # Should sync from Discord to CMS
        sync_manager.sync_from_discord.assert_called_once()

    def test_detect_conflict_no_conflict(self, sync_manager):
        """Test conflict detection when no conflict exists"""
        current_state = None  # No existing state
        new_changes = {'name': 'New Task'}
        source = 'cms'

        conflict = sync_manager._detect_conflict(current_state, new_changes, source)

        assert conflict is None

    def test_detect_conflict_with_conflict(self, sync_manager):
        """Test conflict detection when conflict exists"""
        current_state = {
            'name': 'Old Name',
            'last_modified': '2025-01-01T10:00:00',
            'source': 'discord'
        }
        new_changes = {'name': 'New Name'}
        source = 'cms'

        conflict = sync_manager._detect_conflict(current_state, new_changes, source)

        assert conflict is not None
        assert len(conflict['conflicts']) == 1
        assert conflict['conflicts'][0]['field'] == 'name'

    @pytest.mark.asyncio
    async def test_resolve_conflict_last_modified(self, sync_manager):
        """Test conflict resolution using last modified strategy"""
        sync_manager.auto_resolve_strategy = SyncConflictResolution.LAST_MODIFIED

        conflict = {
            'current_state': {'last_modified': '2025-01-01T10:00:00'},
            'new_changes': {'name': 'New Name'}
        }

        resolution = await sync_manager._resolve_conflict(conflict, SyncEntity.TASK, 'task_123', 123456789)

        assert resolution['action'] == 'apply_new'
        assert resolution['reason'] == 'newer_change'

    @pytest.mark.asyncio
    async def test_resolve_conflict_cms_wins(self, sync_manager):
        """Test conflict resolution with CMS priority"""
        sync_manager.auto_resolve_strategy = SyncConflictResolution.CMS_WINS

        conflict = {
            'current_state': {'name': 'Discord Name'},
            'new_changes': {'name': 'CMS Name'}
        }

        resolution = await sync_manager._resolve_conflict(conflict, SyncEntity.TASK, 'task_123', 123456789)

        assert resolution['action'] == 'apply_new'
        assert resolution['reason'] == 'cms_priority'

    @pytest.mark.asyncio
    async def test_resolve_conflict_manual(self, sync_manager):
        """Test conflict resolution requiring manual intervention"""
        sync_manager.auto_resolve_strategy = SyncConflictResolution.MANUAL

        conflict = {
            'current_state': {'name': 'Discord Name'},
            'new_changes': {'name': 'CMS Name'}
        }

        resolution = await sync_manager._resolve_conflict(conflict, SyncEntity.TASK, 'task_123', 123456789)

        assert resolution['action'] == 'skip'
        assert resolution['reason'] == 'manual_resolution_required'

        # Check that conflict was queued
        assert len(sync_manager.conflict_queue) == 1

    def test_merge_changes_success(self, sync_manager):
        """Test successful change merging"""
        current_state = {'name': 'Task', 'description': ''}
        new_changes = {'name': 'Updated Task', 'description': 'New description'}

        merged = sync_manager._merge_changes(current_state, new_changes)

        assert merged is not None
        assert merged['name'] == 'Updated Task'
        assert merged['description'] == 'New description'

    def test_merge_changes_conflict(self, sync_manager):
        """Test failed change merging due to conflict"""
        current_state = {'name': 'Task A'}
        new_changes = {'name': 'Task B'}

        merged = sync_manager._merge_changes(current_state, new_changes)

        assert merged is None  # Cannot merge conflicting changes

    @pytest.mark.asyncio
    async def test_apply_to_discord_task(self, sync_manager):
        """Test applying task changes to Discord"""
        # Mock bot and guild
        mock_bot = Mock()
        mock_guild = Mock()
        mock_channel = AsyncMock()
        mock_message = AsyncMock()

        mock_bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel
        mock_channel.fetch_message.return_value = mock_message

        sync_manager.data_manager.bot_instance = mock_bot

        # Mock task data
        sync_manager.data_manager.load_guild_data.return_value = {
            'tasks': {
                'task_123': {
                    'name': 'Test Task',
                    'description': 'Test description',
                    'reward': 100,
                    'message_id': 'msg_456'
                }
            }
        }

        result = await sync_manager._apply_to_discord(SyncEntity.TASK, 'task_123', 123456789, {})

        assert result['success'] == True
        mock_message.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_to_discord_shop_item(self, sync_manager):
        """Test applying shop item changes to Discord"""
        # Mock bot and guild
        mock_bot = Mock()
        mock_guild = Mock()
        mock_channel = AsyncMock()
        mock_message = AsyncMock()

        mock_bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel
        mock_channel.fetch_message.return_value = mock_message

        sync_manager.data_manager.bot_instance = mock_bot

        # Mock shop data
        sync_manager.data_manager.load_guild_data.return_value = {
            'currency': {
                'shop_items': {
                    'item_123': {
                        'name': 'Test Item',
                        'description': 'Test description',
                        'price': 50,
                        'message_id': 'msg_456'
                    }
                }
            }
        }

        result = await sync_manager._apply_to_discord(SyncEntity.SHOP_ITEM, 'item_123', 123456789, {})

        assert result['success'] == True
        mock_message.edit.assert_called_once()

    def test_get_sync_stats(self, sync_manager):
        """Test getting synchronization statistics"""
        # Add some mock sync state
        sync_manager.sync_state = {
            'guild1:task:task1': {'version': 1},
            'guild1:task:task2': {'version': 2},
            'guild2:shop:shop1': {'version': 1}
        }

        sync_manager.pending_changes = {
            'guild1': [{'action': 'update'}],
            'guild2': [{'action': 'create'}, {'action': 'delete'}]
        }

        sync_manager.conflict_queue = [{'conflict': 'test'}, {'conflict': 'test2'}]

        # Add some mock locks
        sync_manager.sync_locks = {
            'lock1': asyncio.Lock(),
            'lock2': asyncio.Lock()
        }

        stats = sync_manager.get_sync_stats()

        assert stats['active_syncs'] == 3
        assert stats['pending_changes'] == 3
        assert stats['conflicts_queued'] == 2
        assert stats['sync_locks'] == 2

    def test_cleanup_old_sync_state(self, sync_manager):
        """Test cleanup of old sync state entries"""
        # Set up mock sync state with old and new entries
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        new_time = datetime.now(timezone.utc) - timedelta(hours=1)

        sync_manager.sync_state = {
            'old_entry': {'last_modified': old_time.isoformat()},
            'new_entry': {'last_modified': new_time.isoformat()},
            'no_timestamp': {}  # Should be kept
        }

        removed_count = sync_manager.cleanup_old_sync_state(max_age_hours=24)

        assert removed_count == 1
        assert 'old_entry' not in sync_manager.sync_state
        assert 'new_entry' in sync_manager.sync_state
        assert 'no_timestamp' in sync_manager.sync_state

    def test_get_entity_state(self, sync_manager):
        """Test getting entity sync state"""
        sync_manager.sync_state = {
            '123456789:task:task_123': {'version': 2, 'name': 'Test Task'}
        }

        state = sync_manager._get_entity_state(SyncEntity.TASK, 'task_123', 123456789)

        assert state is not None
        assert state['version'] == 2
        assert state['name'] == 'Test Task'

    def test_update_sync_state(self, sync_manager):
        """Test updating entity sync state"""
        sync_manager._update_sync_state(
            entity_type=SyncEntity.TASK,
            entity_id='task_123',
            guild_id=123456789,
            changes={'name': 'Updated Task', 'status': 'active'},
            source='cms'
        )

        state_key = '123456789:task:task_123'
        assert state_key in sync_manager.sync_state

        state = sync_manager.sync_state[state_key]
        assert state['name'] == 'Updated Task'
        assert state['status'] == 'active'
        assert state['source'] == 'cms'
        assert 'last_modified' in state
        assert state['version'] == 1

    def test_compare_states_cms_newer(self, sync_manager):
        """Test state comparison when CMS has newer data"""
        cms_state = {'last_modified': '2025-01-01T12:00:00'}
        discord_state = {'last_modified': '2025-01-01T10:00:00'}

        actions = sync_manager._compare_states(cms_state, discord_state, SyncEntity.TASK, 'task_123', 123456789)

        assert len(actions) == 1
        assert actions[0]['direction'] == 'cms_to_discord'

    def test_compare_states_discord_newer(self, sync_manager):
        """Test state comparison when Discord has newer data"""
        cms_state = {'last_modified': '2025-01-01T10:00:00'}
        discord_state = {'last_modified': '2025-01-01T12:00:00'}

        actions = sync_manager._compare_states(cms_state, discord_state, SyncEntity.TASK, 'task_123', 123456789)

        assert len(actions) == 1
        assert actions[0]['direction'] == 'discord_to_cms'

    def test_compare_states_no_states(self, sync_manager):
        """Test state comparison when neither side has state"""
        actions = sync_manager._compare_states(None, None, SyncEntity.TASK, 'task_123', 123456789)

        assert len(actions) == 0

    def test_compare_states_only_cms(self, sync_manager):
        """Test state comparison when only CMS has state"""
        cms_state = {'name': 'Test Task'}
        discord_state = None

        actions = sync_manager._compare_states(cms_state, discord_state, SyncEntity.TASK, 'task_123', 123456789)

        assert len(actions) == 1
        assert actions[0]['direction'] == 'cms_to_discord'

    def test_compare_states_only_discord(self, sync_manager):
        """Test state comparison when only Discord has state"""
        cms_state = None
        discord_state = {'name': 'Test Task'}

        actions = sync_manager._compare_states(cms_state, discord_state, SyncEntity.TASK, 'task_123', 123456789)

        assert len(actions) == 1
        assert actions[0]['direction'] == 'discord_to_cms'

    def test_get_data_type_for_entity(self, sync_manager):
        """Test getting data type string for entity types"""
        assert sync_manager._get_data_type_for_entity(SyncEntity.TASK) == 'tasks'
        assert sync_manager._get_data_type_for_entity(SyncEntity.SHOP_ITEM) == 'currency'
        assert sync_manager._get_data_type_for_entity(SyncEntity.ANNOUNCEMENT) == 'announcements'
        assert sync_manager._get_data_type_for_entity(SyncEntity.EMBED) == 'embeds'
        assert sync_manager._get_data_type_for_entity(SyncEntity.CONFIG) == 'config'
        assert sync_manager._get_data_type_for_entity(SyncEntity.USER_BALANCE) == 'currency'

    def test_get_container_key_for_entity(self, sync_manager):
        """Test getting container key for entity types"""
        assert sync_manager._get_container_key_for_entity(SyncEntity.TASK) == 'tasks'
        assert sync_manager._get_container_key_for_entity(SyncEntity.SHOP_ITEM) == 'shop_items'
        assert sync_manager._get_container_key_for_entity(SyncEntity.ANNOUNCEMENT) == 'announcements'
        assert sync_manager._get_container_key_for_entity(SyncEntity.EMBED) == 'embeds'
        assert sync_manager._get_container_key_for_entity(SyncEntity.USER_BALANCE) == 'users'
