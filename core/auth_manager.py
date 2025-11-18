"""
Enhanced Authentication Manager for CMS-Discord Integration
Provides comprehensive session management, role synchronization, and security features.
"""

import hashlib
import secrets
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Any
import jwt
from functools import wraps

logger = logging.getLogger(__name__)

class AuthManager:
    """Enhanced authentication manager with session management and role sync"""

    def __init__(self, data_manager, jwt_secret: str, session_timeout: int = 3600):
        self.data_manager = data_manager
        self.jwt_secret = jwt_secret
        self.session_timeout = session_timeout
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.refresh_tokens: Dict[str, Dict[str, Any]] = {}

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

                return {
                    'username': username,
                    'role': 'superadmin' if user_data.get('is_superadmin') else 'admin',
                    'user_id': user_data.get('id'),
                    'permissions': self._get_user_permissions(user_data)
                }
            else:
                self._record_failed_attempt(username)
                return None

        except Exception as e:
            logger.error(f"Authentication error for {username}: {e}")
            return None

    def create_session(self, user_data: Dict[str, Any]) -> str:
        """Create a new authenticated session"""
        session_id = secrets.token_hex(32)
        refresh_token = secrets.token_hex(64)

        now = time.time()
        self.sessions[session_id] = {
            'user': user_data,
            'created_at': now,
            'expires_at': now + self.session_timeout,
            'refresh_token': refresh_token,
            'ip_address': None,  # Set by middleware
            'user_agent': None   # Set by middleware
        }

        self.refresh_tokens[refresh_token] = {
            'session_id': session_id,
            'expires_at': now + (30 * 24 * 60 * 60)  # 30 days
        }

        logger.info(f"Session created for user: {user_data['username']}")
        return session_id

    def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Validate session and return user data if valid"""
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]
        now = time.time()

        # Check if session expired
        if now > session['expires_at']:
            self.destroy_session(session_id)
            return None

        # Extend session if it's close to expiry
        if session['expires_at'] - now < 300:  # Less than 5 minutes left
            session['expires_at'] = now + self.session_timeout
            logger.debug(f"Session extended for user: {session['user']['username']}")

        return session['user']

    def refresh_session(self, refresh_token: str) -> Optional[str]:
        """Refresh an expired session using refresh token"""
        if refresh_token not in self.refresh_tokens:
            return None

        token_data = self.refresh_tokens[refresh_token]
        now = time.time()

        if now > token_data['expires_at']:
            # Refresh token expired
            self.destroy_session(token_data['session_id'])
            return None

        session_id = token_data['session_id']
        if session_id not in self.sessions:
            return None

        # Create new session
        session = self.sessions[session_id]
        new_session_id = self.create_session(session['user'])

        # Clean up old session
        self.destroy_session(session_id)

        return new_session_id

    def destroy_session(self, session_id: str):
        """Destroy a session and its refresh token"""
        if session_id in self.sessions:
            refresh_token = self.sessions[session_id].get('refresh_token')
            if refresh_token and refresh_token in self.refresh_tokens:
                del self.refresh_tokens[refresh_token]
            del self.sessions[session_id]
            logger.info(f"Session destroyed: {session_id}")

    def update_session_info(self, session_id: str, ip_address: str = None, user_agent: str = None):
        """Update session metadata"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if ip_address:
                session['ip_address'] = ip_address
            if user_agent:
                session['user_agent'] = user_agent

    def cleanup_expired_sessions(self):
        """Clean up expired sessions and refresh tokens"""
        now = time.time()
        expired_sessions = []
        expired_refresh_tokens = []

        # Find expired sessions
        for session_id, session in self.sessions.items():
            if now > session['expires_at']:
                expired_sessions.append(session_id)

        # Find expired refresh tokens
        for token, token_data in self.refresh_tokens.items():
            if now > token_data['expires_at']:
                expired_refresh_tokens.append(token)

        # Clean up
        for session_id in expired_sessions:
            del self.sessions[session_id]

        for token in expired_refresh_tokens:
            del self.refresh_tokens[token]

        if expired_sessions or expired_refresh_tokens:
            logger.info(f"Cleaned up {len(expired_sessions)} sessions and {len(expired_refresh_tokens)} refresh tokens")

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
        """Get session statistics for monitoring"""
        now = time.time()
        active_sessions = len([s for s in self.sessions.values() if now <= s['expires_at']])
        expired_sessions = len(self.sessions) - active_sessions

        return {
            'active_sessions': active_sessions,
            'expired_sessions': expired_sessions,
            'total_sessions': len(self.sessions),
            'refresh_tokens': len(self.refresh_tokens),
            'locked_accounts': len([u for u in self.login_attempts.values() if u.get('locked_until', 0) > now])
        }


# Flask middleware decorators
def session_required(auth_manager: AuthManager):
    """Decorator to require valid session"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify

            session_id = request.cookies.get('session_id')
            if not session_id:
                return jsonify({'error': 'Authentication required'}), 401

            user_data = auth_manager.validate_session(session_id)
            if not user_data:
                return jsonify({'error': 'Session expired or invalid'}), 401

            # Update session info
            auth_manager.update_session_info(
                session_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )

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
