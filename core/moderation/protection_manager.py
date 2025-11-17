import logging
from typing import Dict, List, Optional
import discord
from core.data_manager import DataManager

logger = logging.getLogger(__name__)

class ProtectionManager:
    """Manages profanity and link protection settings per guild"""

    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
        self._cache = {}  # guild_id -> config

    def load_protection_config(self, guild_id: int) -> dict:
        """Loads profanity/link protection settings for a guild"""
        if guild_id in self._cache:
            return self._cache[guild_id]

        config_data = self.data_manager.load_guild_data(guild_id, 'config')
        protection_config = config_data.get('moderation', {})

        # Default config if not set
        if not protection_config:
            protection_config = {
                'enabled': True,
                'profanity_filter': True,
                'link_filter': True,
                'profanity_level': 'moderate',  # off, monitor, moderate, strict
                'auto_actions': {
                    'warn': True,
                    'mute': False,
                    'kick': False,
                    'ban': False
                },
                'whitelist_domains': [],
                'blacklist_domains': [],
                'custom_profanity': [],
                'exempt_roles': [],
                'exempt_channels': [],
                'log_channel': None
            }

        self._cache[guild_id] = protection_config
        return protection_config

    def save_protection_config(self, guild_id: int, protection_config: dict) -> bool:
        """Persists updated protection settings to DB and updates cache"""
        try:
            config_data = self.data_manager.load_guild_data(guild_id, 'config')
            config_data['moderation'] = protection_config
            success = self.data_manager.save_guild_data(guild_id, 'config', config_data)

            if success:
                self._cache[guild_id] = protection_config.copy()
                # Broadcast SSE event
                self.data_manager.broadcast_event('moderation_config_update', {
                    'guild_id': guild_id,
                    'config': protection_config
                })
                logger.info(f"Updated protection config for guild {guild_id}")

            return success
        except Exception as e:
            logger.error(f"Failed to save protection config for guild {guild_id}: {e}")
            return False

    def get_profanity_list(self, guild_id: int) -> list:
        """Returns the effective profanity list for the guild"""
        config = self.load_protection_config(guild_id)
        # For now, return default list + custom words
        default_words = [
            'damn', 'hell', 'crap', 'ass', 'bastard', 'bitch', 'shit', 'fuck',
            'cunt', 'dick', 'pussy', 'cock', 'tits', 'boobs', 'nigger', 'faggot'
        ]
        custom_words = config.get('custom_profanity', [])
        return list(set(default_words + custom_words))

    def add_profanity_word(self, guild_id: int, word: str, admin_id: int) -> tuple:
        """Adds a word/phrase to guild blacklist with metadata"""
        config = self.load_protection_config(guild_id)
        custom_profanity = config.setdefault('custom_profanity', [])

        if word.lower() in [w.lower() for w in custom_profanity]:
            return False, "Word already in list"

        custom_profanity.append(word.lower())
        success = self.save_protection_config(guild_id, config)

        if success:
            logger.info(f"Added profanity word '{word}' to guild {guild_id} by admin {admin_id}")

        return success, custom_profanity

    def remove_profanity_word(self, guild_id: int, word: str, admin_id: int) -> tuple:
        """Removes a word from guild blacklist"""
        config = self.load_protection_config(guild_id)
        custom_profanity = config.get('custom_profanity', [])

        if word.lower() not in [w.lower() for w in custom_profanity]:
            return False, "Word not in list"

        custom_profanity = [w for w in custom_profanity if w.lower() != word.lower()]
        config['custom_profanity'] = custom_profanity
        success = self.save_protection_config(guild_id, config)

        if success:
            logger.info(f"Removed profanity word '{word}' from guild {guild_id} by admin {admin_id}")

        return success, custom_profanity

    def get_link_whitelist(self, guild_id: int) -> list:
        """Returns permitted domains/URL patterns for links"""
        config = self.load_protection_config(guild_id)
        return config.get('whitelist_domains', [])

    def add_whitelist_domain(self, guild_id: int, domain_or_regex: str, admin_id: int) -> bool:
        """Adds domain or pattern to whitelist to allow links from trusted sources"""
        config = self.load_protection_config(guild_id)
        whitelist = config.setdefault('whitelist_domains', [])

        if domain_or_regex in whitelist:
            return False

        whitelist.append(domain_or_regex)
        success = self.save_protection_config(guild_id, config)

        if success:
            logger.info(f"Added whitelist domain '{domain_or_regex}' to guild {guild_id} by admin {admin_id}")

        return success

    def remove_whitelist_domain(self, guild_id: int, domain_or_regex: str, admin_id: int) -> bool:
        """Removes domain/pattern from whitelist"""
        config = self.load_protection_config(guild_id)
        whitelist = config.get('whitelist_domains', [])

        if domain_or_regex not in whitelist:
            return False

        whitelist.remove(domain_or_regex)
        config['whitelist_domains'] = whitelist
        success = self.save_protection_config(guild_id, config)

        if success:
            logger.info(f"Removed whitelist domain '{domain_or_regex}' from guild {guild_id} by admin {admin_id}")

        return success

    def is_exempt_from_protection(self, guild_id: int, user_id: int, channel_id: int, roles: List[discord.Role]) -> bool:
        """Determines if a message author or channel is exempt"""
        config = self.load_protection_config(guild_id)

        # Check exempt roles
        exempt_role_ids = config.get('exempt_roles', [])
        user_role_ids = [role.id for role in roles]
        if any(role_id in exempt_role_ids for role_id in user_role_ids):
            return True

        # Check exempt channels
        exempt_channel_ids = config.get('exempt_channels', [])
        if channel_id in exempt_channel_ids:
            return True

        return False

    def on_guild_config_reload(self, guild_id: int):
        """Handler that reloads and re-applies protection config"""
        # Clear cache to force reload
        self._cache.pop(guild_id, None)
        logger.info(f"Reloaded protection config for guild {guild_id}")
