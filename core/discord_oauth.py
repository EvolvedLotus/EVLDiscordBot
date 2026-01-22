"""
Discord OAuth2 Authentication Handler
Provides Discord OAuth2 login for server owners to access the CMS
"""

import os
import logging
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class DiscordOAuthManager:
    """Manages Discord OAuth2 authentication for CMS access"""
    
    def __init__(self, data_manager, auth_manager):
        self.data_manager = data_manager
        self.auth_manager = auth_manager
        
        # Discord OAuth2 Configuration
        self.client_id = os.getenv('DISCORD_CLIENT_ID')
        self.client_secret = os.getenv('DISCORD_CLIENT_SECRET')
        self.redirect_uri = os.getenv('DISCORD_REDIRECT_URI', 'https://evolvedlotus.github.io/EVLDiscordBot/auth/callback')
        
        # Discord API endpoints
        self.discord_api_base = 'https://discord.com/api/v10'
        self.token_url = f'{self.discord_api_base}/oauth2/token'
        self.user_url = f'{self.discord_api_base}/users/@me'
        self.guilds_url = f'{self.discord_api_base}/users/@me/guilds'
        
        # OAuth2 scopes
        self.scopes = ['identify', 'guilds']
        
        if not self.client_id or not self.client_secret:
            logger.warning("⚠️ Discord OAuth2 not configured - server owner login disabled")
    
    def get_authorization_url(self, state: str = None) -> str:
        """
        Generate Discord OAuth2 authorization URL
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL to redirect user to
        """
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.scopes)
        }
        
        if state:
            params['state'] = state
        
        return f'https://discord.com/api/oauth2/authorize?{urlencode(params)}'
    
    async def exchange_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Exchange authorization code for access token
        
        Args:
            code: Authorization code from Discord
            
        Returns:
            Token data including access_token, refresh_token, expires_in
        """
        try:
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': self.redirect_uri
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.token_url, data=data, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Discord token exchange failed: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Error exchanging Discord code: {e}")
            return None
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Refresh Discord access token
        
        Args:
            refresh_token: Discord refresh token
            
        Returns:
            New token data
        """
        try:
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.token_url, data=data, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Discord token refresh failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error refreshing Discord token: {e}")
            return None
    
    async def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Get Discord user information
        
        Args:
            access_token: Discord access token
            
        Returns:
            User info including id, username, avatar
        """
        try:
            headers = {
                'Authorization': f'Bearer {access_token}'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.user_url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Discord user info fetch failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error getting Discord user info: {e}")
            return None
    
    async def get_user_guilds(self, access_token: str) -> List[Dict[str, Any]]:
        """
        Get guilds the user is in (and owns)
        
        Args:
            access_token: Discord access token
            
        Returns:
            List of guilds with ownership information
        """
        try:
            headers = {
                'Authorization': f'Bearer {access_token}'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.guilds_url, headers=headers) as response:
                    if response.status == 200:
                        guilds = await response.json()
                        # Filter to only guilds where user is owner
                        # Discord permissions: 0x1 (OWNER) is included in permissions
                        owned_guilds = [
                            g for g in guilds 
                            if g.get('owner') or (int(g.get('permissions', 0)) & 0x8) == 0x8  # ADMINISTRATOR
                        ]
                        return owned_guilds
                    else:
                        logger.error(f"Discord guilds fetch failed: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error getting Discord user guilds: {e}")
            return []
    
    async def authenticate_discord_user(self, code: str, ip_address: str = None) -> Optional[Dict[str, Any]]:
        """
        Complete Discord OAuth2 authentication flow
        
        Args:
            code: Authorization code from Discord
            ip_address: User's IP address for logging
            
        Returns:
            User data with session token
        """
        try:
            # 1. Exchange code for tokens
            token_data = await self.exchange_code(code)
            if not token_data:
                return None
            
            access_token = token_data['access_token']
            refresh_token = token_data['refresh_token']
            expires_in = token_data['expires_in']
            
            # 2. Get user info
            user_info = await self.get_user_info(access_token)
            if not user_info:
                return None
            
            discord_id = user_info['id']
            discord_username = f"{user_info['username']}#{user_info['discriminator']}" if user_info.get('discriminator') != '0' else user_info['username']
            discord_avatar = user_info.get('avatar')
            
            # 3. Get user's owned guilds
            owned_guilds = await self.get_user_guilds(access_token)
            owned_guild_ids = [g['id'] for g in owned_guilds]
            
            # Filter to only guilds where bot is present
            bot_guild_ids = await self._get_bot_guild_ids()
            valid_guild_ids = [gid for gid in owned_guild_ids if gid in bot_guild_ids]
            
            if not valid_guild_ids:
                logger.warning(f"Discord user {discord_username} owns no guilds where bot is present")
                return {
                    'error': 'no_guilds',
                    'message': 'You must own a server where the bot is installed to access the CMS'
                }
            
            # 4. Create or update user in database
            token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            user_id = self.data_manager.admin_client.rpc(
                'upsert_discord_user',
                {
                    'p_discord_id': discord_id,
                    'p_discord_username': discord_username,
                    'p_discord_avatar': discord_avatar,
                    'p_access_token': access_token,
                    'p_refresh_token': refresh_token,
                    'p_token_expires_at': token_expires_at.isoformat(),
                    'p_owned_guild_ids': valid_guild_ids
                }
            ).execute()
            
            # 5. Log OAuth login
            self.data_manager.admin_client.table('discord_oauth_logs').insert({
                'user_id': user_id.data,
                'discord_id': discord_id,
                'action': 'login',
                'ip_address': ip_address,
                'guilds_synced': valid_guild_ids
            }).execute()
            
            # Fetch user record to check superadmin status
            db_user_result = self.data_manager.admin_client.table('admin_users').select('is_superadmin').eq('id', user_id.data).single().execute()
            is_superadmin = False
            if db_user_result.data:
                is_superadmin = db_user_result.data.get('is_superadmin', False)

            # 6. Create CMS session
            user_data = {
                'id': user_id.data,
                'username': discord_username,
                'discord_id': discord_id,
                'discord_avatar': discord_avatar,
                'is_superadmin': is_superadmin,
                'allowed_guild_ids': valid_guild_ids,
                'login_type': 'discord',
                'role': 'superadmin' if is_superadmin else 'server_owner',
                'permissions': ['read', 'write', 'delete', 'admin'] if is_superadmin else ['read', 'write']
            }
            
            session_token = self.auth_manager.create_session(user_data)
            
            logger.info(f"✅ Discord OAuth login successful: {discord_username} (guilds: {len(valid_guild_ids)})")
            
            return {
                'success': True,
                'user': user_data,
                'session_token': session_token,
                'guilds': owned_guilds
            }
            
        except Exception as e:
            logger.error(f"Discord authentication error: {e}", exc_info=True)
            return None
    
    async def _get_bot_guild_ids(self) -> List[str]:
        """Get list of guild IDs where bot is present"""
        try:
            result = self.data_manager.admin_client.table('guilds').select('guild_id').eq('is_active', True).execute()
            return [g['guild_id'] for g in result.data]
        except Exception as e:
            logger.error(f"Error fetching bot guild IDs: {e}")
            return []
    
    def verify_guild_access(self, user_data: Dict[str, Any], guild_id: str) -> bool:
        """
        Verify if user has access to a specific guild
        
        Args:
            user_data: User session data
            guild_id: Guild ID to check access for
            
        Returns:
            True if user has access, False otherwise
        """
        # Superadmins have access to all guilds
        if user_data.get('is_superadmin'):
            return True
        
        # Check if guild is in user's allowed list
        allowed_guilds = user_data.get('allowed_guild_ids', [])
        return guild_id in allowed_guilds
    
    async def sync_user_guilds(self, user_id: str) -> bool:
        """
        Re-sync user's guild ownership (called periodically or on demand)
        
        Args:
            user_id: User ID to sync
            
        Returns:
            True if sync successful
        """
        try:
            # Get user's current Discord tokens
            result = self.data_manager.admin_client.table('admin_users').select(
                'discord_id, discord_access_token, discord_refresh_token, discord_token_expires_at'
            ).eq('id', user_id).single().execute()
            
            if not result.data:
                return False
            
            user = result.data
            access_token = user['discord_access_token']
            
            # Check if token needs refresh
            if user['discord_token_expires_at']:
                expires_at = datetime.fromisoformat(user['discord_token_expires_at'].replace('Z', '+00:00'))
                if expires_at < datetime.now(timezone.utc):
                    # Refresh token
                    token_data = await self.refresh_access_token(user['discord_refresh_token'])
                    if token_data:
                        access_token = token_data['access_token']
                        # Update tokens in database
                        self.data_manager.admin_client.table('admin_users').update({
                            'discord_access_token': access_token,
                            'discord_refresh_token': token_data.get('refresh_token', user['discord_refresh_token']),
                            'discord_token_expires_at': (datetime.now(timezone.utc) + timedelta(seconds=token_data['expires_in'])).isoformat()
                        }).eq('id', user_id).execute()
            
            # Get current owned guilds
            owned_guilds = await self.get_user_guilds(access_token)
            owned_guild_ids = [g['id'] for g in owned_guilds]
            
            # Filter to bot guilds
            bot_guild_ids = await self._get_bot_guild_ids()
            valid_guild_ids = [gid for gid in owned_guild_ids if gid in bot_guild_ids]
            
            # Update database
            self.data_manager.admin_client.rpc(
                'sync_discord_user_guilds',
                {
                    'p_discord_id': user['discord_id'],
                    'p_owned_guild_ids': valid_guild_ids
                }
            ).execute()
            
            logger.info(f"✅ Synced guilds for user {user_id}: {len(valid_guild_ids)} guilds")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing user guilds: {e}")
            return False
