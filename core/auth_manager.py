"""
Enhanced Authentication Manager for CMS-Discord Integration
Provides comprehensive session management, role synchronization, and security features.
Now backed by Database (Supabase) for sessions instead of memory.
"""

import hashlib
import secrets
import time
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Any
import jwt
from functools import wraps

logger = logging.getLogger(__name__)

class AuthManager:
    """Enhanced authentication manager with DB-backed session management and role sync"""

    def __init__(self, data_manager, jwt_secret: str, session_timeout: int = 3600):
        self.data_manager = data_manager
        self.jwt_secret = jwt_secret
        self.session_timeout = session_timeout
        
        # Security settings
        self.max_login_attempts = 5
        self.lockout_duration = 900  # 15 minutes
        self.login_attempts: Dict[str, Dict[str, Any]] = {}

        # Admin user cache
        self.admin_users_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_timeout = 300  # 5 minutes

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user with enhanced security"""
        # Check for account lockout
        if self._is_account_locked(username):
            logger.warning(f"Login attempt for locked account: {username}")
            return None

        try:
            # Load admin users from database
            admin_users = self._load_admin_users()

            if username not in admin_users:
                logger.warning(f"Authentication failed: User '{username}' not found in admin_users table")
                self._record_failed_attempt(username)
                return None

            user_data = admin_users[username]

            if not user_data.get('is_active', True):
                logger.warning(f"Login attempt for inactive user: {username}")
                return None

            # Verify password
            hashed_password = self._hash_password(password)
            stored_hash = user_data.get('password_hash', '')

            if hashed_password == stored_hash:
                # Successful login - clear failed attempts
                self._clear_failed_attempts(username)

                # Update last login
                self._update_last_login(username)

                # Calculate session expiry
                session_expires = datetime.now(timezone.utc) + timedelta(hours=24)

                return {
                    'id': user_data.get('id'),
                    'username': username,
                    'role': 'superadmin' if user_data.get('is_superadmin') else 'admin',
                    'is_superadmin': user_data.get('is_superadmin', False),
                    'permissions': self._get_user_permissions(user_data),
                    'session_expires': session_expires
                }
            else:
                logger.warning(f"Authentication failed: Password mismatch for user '{username}'")
                self._record_failed_attempt(username)
                return None

        except Exception as e:
            logger.error(f"Authentication error for {username}: {e}")
            return None

    def create_session(self, user_data: Dict[str, Any]) -> str:
        """Create a new authenticated session in database"""
        session_id = secrets.token_hex(32)
        
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.session_timeout)
            
            # Insert into web_sessions
            self.data_manager.admin_client.table('web_sessions').insert({
                'session_id': session_id,
                'user_id': str(user_data.get('id', '')),
                'user_data': user_data,
                'expires_at': expires_at.isoformat(),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'is_valid': True
            }).execute()

            logger.info(f"Session created for user: {user_data.get('username')} (DB)")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to create DB session: {e}", exc_info=True)
            # Fallback to minimal JWT or error? 
            # For now, return empty which will fail auth, prompting retry/error.
            raise e

    def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Validate session from database and return user data if valid"""
        if not session_id:
            return None

        try:
            # Check DB
            result = self.data_manager.admin_client.table('web_sessions') \
                .select('*') \
                .eq('session_id', session_id) \
                .eq('is_valid', True) \
                .execute()
            
            if not result.data or len(result.data) == 0:
                return None
                
            session = result.data[0]
            
            # Parse expires_at (Supabase returns ISO string)
            # Handle Z format or offset
            expires_str = session['expires_at']
            expires_at = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            
            # Check expiry
            if now > expires_at:
                self.destroy_session(session_id)
                return None
                
            # Extend session if active (sliding window) - optimize to not do every request?
            # Let's simple implementation: Update expiry if < 5 mins left
            time_left = (expires_at - now).total_seconds()
            if time_left < 300:
                new_expires = now + timedelta(seconds=self.session_timeout)
                self.data_manager.admin_client.table('web_sessions') \
                    .update({'expires_at': new_expires.isoformat()}) \
                    .eq('session_id', session_id) \
                    .execute()
                logger.debug(f"Session extended for user: {session['user_id']}")
                
            return session['user_data']
            
        except Exception as e:
            # Don't spam logs on common invalid sessions?
            logger.error(f"Error validating session: {e}")
            return None

    def refresh_session(self, refresh_token: str) -> Optional[str]:
        """
        Refresh mechanisms usually require a separate refresh_token table or logic.
        The previous in-memory implementation had self.refresh_tokens.
        For now, since we have sliding expiration in validate_session, distinct refresh tokens might not be needed 
        unless we want long-lived "Remember Me".
        
        Original code tracked refresh tokens. Let's rely on validate_session extending the time 
        OR implement full refresh token support in DB.
        
        Given task "Store session IDs server-side", simpler is robust DB session.
        If user is active, session extends. If they leave for > 1 hour, they rely on 'permanent' cookie?
        Config says PERMANENT_SESSION_LIFETIME = 24 hours.
        
        I'll skip complex refresh_token logic for now and assume the session_id IS the token.
        """
        return None

    def destroy_session(self, session_id: str):
        """Destroy a session in database"""
        try:
            self.data_manager.admin_client.table('web_sessions') \
                .delete() \
                .eq('session_id', session_id) \
                .execute()
            logger.info(f"Session destroyed: {session_id}")
        except Exception as e:
            logger.error(f"Error destroying session: {e}")

    def update_session_info(self, session_id: str, ip_address: str = None, user_agent: str = None):
        """Update session metadata in DB"""
        try:
            updates = {}
            if ip_address:
                updates['ip_address'] = ip_address
            if user_agent:
                updates['user_agent'] = user_agent
                
            if updates:
                self.data_manager.admin_client.table('web_sessions') \
                    .update(updates) \
                    .eq('session_id', session_id) \
                    .execute()
        except Exception as e:
            logger.error(f"Error updating session info: {e}")

    def cleanup_expired_sessions(self):
        """Clean up expired sessions from DB"""
        try:
            now = datetime.now(timezone.utc).isoformat()
            self.data_manager.admin_client.table('web_sessions') \
                .delete() \
                .lt('expires_at', now) \
                .execute()
            logger.info("Cleaned up expired sessions from DB")
        except Exception as e:
            logger.error(f"Error cleaning sessions: {e}")

    def create_jwt_token(self, user_data: Dict[str, Any]) -> str:
        """Create JWT access token"""
        payload = {
            'user_id': user_data.get('user_id'),
            'username': user_data.get('username'),
            'role': user_data.get('role'),
            'permissions': user_data.get('permissions', []),
            'iat': datetime.now(timezone.utc),
            'exp': datetime.now(timezone.utc) + timedelta(hours=1)
        }

        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')

    def validate_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def sync_discord_permissions(self, guild_id: int, user_id: int, bot_instance) -> Dict[str, Any]:
        """Sync Discord permissions and roles for a user"""
        try:
            guild = bot_instance.get_guild(guild_id)
            if not guild:
                return {'error': 'Guild not found'}

            member = guild.get_member(user_id)
            if not member:
                return {'error': 'User not in guild'}

            # Get Discord permissions
            permissions = {
                'is_admin': member.guild_permissions.administrator,
                'is_moderator': self._check_moderator_permissions(member),
                'roles': [role.name for role in member.roles if role.name != '@everyone'],
                'role_ids': [str(role.id) for role in member.roles if role.name != '@everyone'],
                'permissions': {
                    'kick_members': member.guild_permissions.kick_members,
                    'ban_members': member.guild_permissions.ban_members,
                    'manage_messages': member.guild_permissions.manage_messages,
                    'manage_channels': member.guild_permissions.manage_channels,
                    'manage_roles': member.guild_permissions.manage_roles,
                    'view_audit_log': member.guild_permissions.view_audit_log
                }
            }

            # Check against configured admin/moderator roles
            config = self.data_manager.load_guild_data(guild_id, 'config')
            admin_roles = config.get('admin_roles', [])
            moderator_roles = config.get('moderator_roles', [])

            permissions['is_admin'] = permissions['is_admin'] or any(str(role.id) in admin_roles for role in member.roles)
            permissions['is_moderator'] = permissions['is_moderator'] or permissions['is_admin'] or any(str(role.id) in moderator_roles for role in member.roles)

            # Update user permissions in database
            self._update_user_permissions(guild_id, user_id, permissions)

            return permissions

        except Exception as e:
            logger.error(f"Error syncing Discord permissions for user {user_id}: {e}")
            return {'error': str(e)}

    def _check_moderator_permissions(self, member) -> bool:
        """Check if user has moderator-level permissions"""
        mod_permissions = [
            'kick_members', 'ban_members', 'manage_messages',
            'manage_channels', 'manage_roles', 'view_audit_log'
        ]

        return any(getattr(member.guild_permissions, perm) for perm in mod_permissions)

    def _update_user_permissions(self, guild_id: int, user_id: int, permissions: Dict[str, Any]):
        """Update user permissions in database"""
        try:
            # This would update a user_permissions table if implemented
            # For now, we'll store in the users table metadata
            currency_data = self.data_manager.load_guild_data(guild_id, 'currency')
            users = currency_data.get('users', {})
            user_key = str(user_id)

            if user_key not in users:
                users[user_key] = {'balance': 0, 'total_earned': 0, 'total_spent': 0}

            users[user_key]['permissions'] = permissions
            users[user_key]['permissions_synced_at'] = datetime.now(timezone.utc).isoformat()

            self.data_manager.save_guild_data(guild_id, 'currency', currency_data)

        except Exception as e:
            logger.error(f"Error updating user permissions: {e}")

    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()

    def _load_admin_users(self) -> Dict[str, Dict[str, Any]]:
        """Load admin users from database with caching"""
        now = time.time()

        # Check cache
        if self.admin_users_cache and (now - self.admin_users_cache.get('_timestamp', 0)) < self.cache_timeout:
            return {k: v for k, v in self.admin_users_cache.items() if k != '_timestamp'}

        try:
            # Load from database
            result = self.data_manager.admin_client.table('admin_users').select('*').execute()

            users = {}
            for user in result.data:
                users[user['username']] = user

            # Update cache
            users['_timestamp'] = now
            self.admin_users_cache = users.copy()

            return {k: v for k, v in users.items() if k != '_timestamp'}

        except Exception as e:
            logger.error(f"Error loading admin users: {e}")
            return {}

    def _record_failed_attempt(self, username: str):
        """Record failed login attempt"""
        now = time.time()

        if username not in self.login_attempts:
            self.login_attempts[username] = {'count': 0, 'first_attempt': now, 'locked_until': 0}

        attempts = self.login_attempts[username]
        attempts['count'] += 1

        # Lock account if too many attempts
        if attempts['count'] >= self.max_login_attempts:
            attempts['locked_until'] = now + self.lockout_duration
            logger.warning(f"Account locked for user: {username}")

    def _clear_failed_attempts(self, username: str):
        """Clear failed login attempts for user"""
        if username in self.login_attempts:
            del self.login_attempts[username]

    def _is_account_locked(self, username: str) -> bool:
        """Check if account is currently locked"""
        if username not in self.login_attempts:
            return False

        attempts = self.login_attempts[username]
        now = time.time()

        # Clear expired lockouts
        if now > attempts.get('locked_until', 0):
            self._clear_failed_attempts(username)
            return False

        return attempts.get('locked_until', 0) > now

    def _update_last_login(self, username: str):
        """Update user's last login timestamp"""
        try:
            self.data_manager.admin_client.table('admin_users').update({
                'last_login': datetime.now(timezone.utc).isoformat()
            }).eq('username', username).execute()
        except Exception as e:
            logger.error(f"Error updating last login for {username}: {e}")

    def _get_user_permissions(self, user_data: Dict[str, Any]) -> List[str]:
        """Get user permissions list"""
        permissions = ['read']

        if user_data.get('is_superadmin'):
            permissions.extend(['write', 'delete', 'admin', 'superadmin'])
        else:
            permissions.extend(['write', 'delete', 'admin'])

        return permissions

    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics for monitoring (approximate from DB)"""
        try:
             # Count query would be better but .count() in supabase-py depends on version/postgrest
             # We'll just return placeholder or minimal info to avoid heavy query default
             return {
                 'status': 'db_managed',
                 'active': 'query_db_to_see'
             }
        except Exception:
             return {}


# Flask middleware decorators
def session_required(auth_manager: AuthManager):
    """Decorator to require valid session"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify

            # Check for session token (support both cookie and header)
            session_id = request.cookies.get('session_token') or request.headers.get('X-Session-Token')
            
            if not session_id:
                return jsonify({'error': 'Authentication required'}), 401

            user_data = auth_manager.validate_session(session_id)
            if not user_data:
                return jsonify({'error': 'Session expired or invalid'}), 401

            # Update session info (async/background preferred, but doing sync for now)
            # auth_manager.update_session_info(...) # Optimize to not do every hit

            # Add user to request context
            request.user = user_data
            return f(*args, **kwargs)
        return wrapper
    return decorator

def jwt_required(auth_manager: AuthManager):
    """Decorator to require valid JWT token"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify

            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return jsonify({'error': 'JWT token required'}), 401

            token = auth_header[7:]  # Remove 'Bearer ' prefix
            user_data = auth_manager.validate_jwt_token(token)

            if not user_data:
                return jsonify({'error': 'Invalid or expired JWT token'}), 401

            # Add user to request context
            request.user = user_data
            return f(*args, **kwargs)
        return wrapper
    return decorator

def permission_required(permission: str):
    """Decorator to require specific permission"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify

            if not hasattr(request, 'user'):
                return jsonify({'error': 'Authentication required'}), 401

            user_permissions = request.user.get('permissions', [])
            if permission not in user_permissions:
                return jsonify({'error': f'Permission required: {permission}'}), 403

            return f(*args, **kwargs)
        return wrapper
    return decorator
