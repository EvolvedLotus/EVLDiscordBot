import re
import logging
from typing import Dict, List, Tuple, Optional
import discord
from .protection_manager import ProtectionManager

logger = logging.getLogger(__name__)

class MessageScanner:
    """Scans messages for profanity and unauthorized links"""

    def __init__(self, protection_manager: ProtectionManager):
        self.protection_manager = protection_manager

    async def scan_message_for_profanity(self, message, guild_id):
        """Scan message content for profanity with whitelist support"""

        # Skip bot messages
        if message.author.bot:
            return None

        # Load protection config
        config = await self.protection_manager.get_config(guild_id)

        if not config or not config.get('profanity_filter_enabled'):
            return None

        # Get profanity list and whitelist
        profanity_list = config.get('profanity_words', [])
        whitelist = config.get('whitelist_words', [])

        content = message.content.lower()

        # Check whitelist first (prevent false positives)
        for whitelisted_word in whitelist:
            if whitelisted_word.lower() in content:
                # If whitelisted word contains profanity, ignore it
                content = content.replace(whitelisted_word.lower(), '')

        # Now check for profanity
        detected_words = []
        for bad_word in profanity_list:
            # Word boundary check to prevent partial matches
            import re
            pattern = r'\b' + re.escape(bad_word.lower()) + r'\b'
            if re.search(pattern, content):
                detected_words.append(bad_word)

        if detected_words:
            return {
                'violation_type': 'profanity',
                'detected_words': detected_words,
                'message_id': str(message.id),
                'user_id': str(message.author.id),
                'channel_id': str(message.channel.id)
            }

        return None

    def scan_message_for_links(self, guild_id: int, message_content: str) -> List[Dict]:
        """Extracts URLs from text and classifies them"""
        config = self.protection_manager.load_protection_config(guild_id)

        if not config.get('link_filter', True):
            return []

        # URL regex pattern
        url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?'
        urls = re.findall(url_pattern, message_content, re.IGNORECASE)

        whitelist = self.protection_manager.get_link_whitelist(guild_id)
        blacklist = config.get('blacklist_domains', [])

        links = []
        for url in urls:
            domain = self._extract_domain(url)
            is_whitelisted = self._check_whitelist(domain, whitelist)
            is_blacklisted = self._check_blacklist(domain, blacklist)

            links.append({
                'url': url,
                'domain': domain,
                'is_whitelisted': is_whitelisted,
                'is_blacklisted': is_blacklisted
            })

        return links

    def scan_attachments_and_embeds(self, guild_id: int, message: discord.Message) -> List[Dict]:
        """Inspects attachments and embed URLs for links and forbidden content"""
        violations = []

        # Check attachments (basic - no OCR implemented yet)
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.exe', '.bat', '.cmd', '.scr', '.pif')):
                violations.append({
                    'type': 'attachment',
                    'filename': attachment.filename,
                    'reason': 'executable_file'
                })

        # Check embed URLs
        for embed in message.embeds:
            if embed.url:
                links = self.scan_message_for_links(guild_id, embed.url)
                for link in links:
                    if link['is_blacklisted']:
                        violations.append({
                            'type': 'embed_url',
                            'url': link['url'],
                            'domain': link['domain'],
                            'reason': 'blacklisted_domain'
                        })

            # Check embed description for links
            if embed.description:
                links = self.scan_message_for_links(guild_id, embed.description)
                for link in links:
                    if link['is_blacklisted']:
                        violations.append({
                            'type': 'embed_description',
                            'url': link['url'],
                            'domain': link['domain'],
                            'reason': 'blacklisted_domain'
                        })

        return violations

    def _normalize_text(self, text: str) -> str:
        """Normalize text for better profanity detection"""
        # Remove common leetspeak substitutions
        replacements = {
            '4': 'a', '@': 'a', '3': 'e', '1': 'i', '!': 'i',
            '0': 'o', '5': 's', '$': 's', '7': 't'
        }

        normalized = text.lower()
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        # Remove extra spaces and punctuation
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return normalized

    def _calculate_severity(self, word: str, level: str) -> str:
        """Calculate severity level for a profanity word"""
        # Simple severity calculation based on word length and level setting
        severe_words = ['fuck', 'cunt', 'nigger', 'faggot']

        if word.lower() in severe_words:
            return 'high'
        elif len(word) > 6:
            return 'medium'
        else:
            return 'low'

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return url.lower()

    def _check_whitelist(self, domain: str, whitelist: List[str]) -> bool:
        """Check if domain matches whitelist patterns"""
        for pattern in whitelist:
            if pattern.startswith('*'):
                # Wildcard pattern
                if domain.endswith(pattern[1:]):
                    return True
            elif pattern == domain:
                return True
        return False

    def _check_blacklist(self, domain: str, blacklist: List[str]) -> bool:
        """Check if domain matches blacklist patterns"""
        for pattern in blacklist:
            if pattern.startswith('*'):
                # Wildcard pattern
                if domain.endswith(pattern[1:]):
                    return True
            elif pattern == domain:
                return True
        return False
