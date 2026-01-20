"""
PRODUCTION-READY BACKEND.PY WITH CORS
Complete backend with all functionality restored
"""

from flask import Flask, request, jsonify, make_response, session, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
import asyncio
from threading import Thread
import hashlib
import secrets
import json
from functools import wraps
import discord

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__, static_folder='docs', static_url_path='')

# Environment detection
IS_PRODUCTION = (
    os.getenv('RAILWAY_ENVIRONMENT') == 'production' or
    os.getenv('ENVIRONMENT') == 'production' or
    os.getenv('RAILWAY_PROJECT_ID') is not None  # Railway-specific detection
)

# Import centralized CORS configuration
try:
    from config import config as app_config
    ALLOWED_ORIGINS = app_config.allowed_origins
    logger.info(f"✅ CORS origins from centralized config: {ALLOWED_ORIGINS}")
except ImportError:
    # Fallback if config not available
    ALLOWED_ORIGINS = [
        'https://evolvedlotus.github.io',
        'https://evolvedlotus.github.io/EVLDiscordBot',
        'http://localhost:3000',
        'http://localhost:5000',
    ]
    logger.warning("⚠️ Using fallback CORS origins - config not available")

CORS(app,
     origins=ALLOWED_ORIGINS,
     supports_credentials=True,
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'],
     expose_headers=['Content-Type', 'X-Total-Count'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
     max_age=3600
)

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Track failed login attempts
failed_login_attempts = {}  # {ip: [(timestamp, username), ...]}

def require_auth(f):
    """Decorator to require valid session"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_token = request.cookies.get('session_token')

        if not session_token:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        # Validate session
        user = auth_manager.validate_session(session_token)

        if not user:
            return jsonify({'success': False, 'error': 'Invalid or expired session'}), 401

        # Check if session needs refresh (expires in < 1 hour)
        # if user['session_expires'] - datetime.now(timezone.utc) < timedelta(hours=1):
            # Refresh session
            # new_expires = datetime.now(timezone.utc) + timedelta(hours=24)
            # auth_manager.refresh_session(session_token, new_expires)

        # Add user to request context
        request.user = user

        return f(*args, **kwargs)

    return decorated_function

def require_guild_access(f):
    """Decorator to require guild access validation"""
    from functools import wraps

    @wraps(f)
    def decorated_function(server_id, *args, **kwargs):
        # First ensure user is authenticated
        session_token = request.cookies.get('session_token')
        if not session_token:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        user = auth_manager.validate_session(session_token)
        if not user:
            return jsonify({'success': False, 'error': 'Invalid or expired session'}), 401

        # Superadmins have access to all guilds
        if user.get('is_superadmin'):
            request.user = user
            return f(server_id, *args, **kwargs)

        # For Discord OAuth users, check allowed_guild_ids
        allowed_guilds = user.get('allowed_guild_ids', [])
        if allowed_guilds and server_id in allowed_guilds:
            request.user = user
            return f(server_id, *args, **kwargs)

        # Fallback: Try to get user guilds from database
        try:
            user_guilds = data_manager.get_user_guilds(user['id'])
            if server_id not in [str(g.get('guild_id', g)) for g in user_guilds]:
                logger.warning(f"Access denied: User {user['id']} attempted to access guild {server_id}")
                return jsonify({'error': 'Access denied to this server'}), 403
        except Exception as e:
            logger.error(f"Error validating guild access for user {user['id']}, guild {server_id}: {e}")
            return jsonify({'error': 'Server error validating access'}), 500

        # Add user to request context
        request.user = user

        return f(server_id, *args, **kwargs)

    return decorated_function

def safe_error_response(error, status_code=500, log_error=True):
    """
    Create a safe error response that doesn't leak sensitive information.
    Only returns user-friendly error messages.
    """
    if log_error and error:
        # Log the full error for debugging (server-side only)
        logger.error(f"API Error: {str(error)}", exc_info=True)

    # User-friendly error messages based on status code
    user_messages = {
        400: 'Bad request - please check your input',
        401: 'Authentication required',
        403: 'Access denied',
        404: 'Resource not found',
        429: 'Too many requests - please try again later',
        500: 'Server error - please try again later'
    }

    message = user_messages.get(status_code, 'An error occurred')

    return jsonify({'error': message}), status_code

# Session configuration
app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-change-me')

if IS_PRODUCTION:
    # Production: Use secure session settings for Railway
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_PATH'] = '/'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

    # Railway-specific domain handling
    railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
    if railway_domain:
        app.config['SESSION_COOKIE_DOMAIN'] = railway_domain
    else:
        app.config['SESSION_COOKIE_DOMAIN'] = None
else:
    # Development: Relaxed session settings
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_PATH'] = '/'
    app.config['SESSION_COOKIE_DOMAIN'] = None
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Import core managers
try:
    from core.data_manager import DataManager
    from core.transaction_manager import TransactionManager
    from core.task_manager import TaskManager
    from core.shop_manager import ShopManager
    from core.announcement_manager import AnnouncementManager
    from core.embed_builder import EmbedBuilder
    from core.embed_manager import EmbedManager
    from core.cache_manager import CacheManager
    from core.auth_manager import AuthManager
    from core.audit_manager import AuditManager
    from core.sync_manager import SyncManager
    from core.sse_manager import sse_manager
    from core.discord_oauth import DiscordOAuthManager
    from core.discord_oauth import DiscordOAuthManager
    from core.ad_claim_manager import AdClaimManager
    from core.tier_manager import TierManager

    # Initialize managers
    data_manager = DataManager()
    cache_manager = CacheManager()
    audit_manager = AuditManager(data_manager)
    auth_manager = AuthManager(data_manager, os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-change-me'))
    discord_oauth_manager = DiscordOAuthManager(data_manager, auth_manager)
    transaction_manager = TransactionManager(data_manager, audit_manager, cache_manager)
    task_manager = TaskManager(data_manager, transaction_manager)
    shop_manager = ShopManager(data_manager, transaction_manager)
    announcement_manager = AnnouncementManager(data_manager)
    embed_builder = EmbedBuilder()
    embed_manager = EmbedManager(data_manager)
    sync_manager = SyncManager(data_manager, audit_manager, sse_manager)
    ad_claim_manager = AdClaimManager(data_manager, transaction_manager)

    logger.info("✅ All managers initialized")
except ImportError as e:
    logger.warning(f"⚠️  Some managers not available: {e}")

# Global bot instance reference
_bot_instance = None

def set_bot_instance(bot):
    """Set the global bot instance"""
    global _bot_instance
    _bot_instance = bot
    # Update managers that need bot reference
    if announcement_manager:
        announcement_manager.set_bot(bot)
    logger.info("✅ Bot instance attached to backend")

def set_data_manager(dm):
    """Set the global data manager (called from bot.py)"""
    global data_manager
    data_manager = dm
    # Update dependent managers
    if auth_manager:
        auth_manager.data_manager = dm
    logger.info("✅ Data manager updated from bot")

# Bot communication functions for Railway internal networking
def get_bot_webhook_url():
    """Get the bot webhook URL for Railway internal communication"""
    if IS_PRODUCTION:
        # In Railway, services communicate using service names
        # The bot service is named 'bot' and runs on port 5001
        return "http://bot:5001"
    else:
        # In development, use localhost
        return "http://localhost:5001"

async def send_admin_message_to_bot(guild_id, channel_id, message, embed_data=None):
    """Send admin message to bot via internal webhook"""
    try:
        import aiohttp

        bot_url = get_bot_webhook_url()
        async with aiohttp.ClientSession() as session:
            payload = {
                'guild_id': str(guild_id),
                'channel_id': str(channel_id),
                'message': message
            }
            if embed_data:
                payload['embed'] = embed_data

            async with session.post(f"{bot_url}/admin_message", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('success', False)
                else:
                    error_text = await response.text()
                    logger.error(f"Bot webhook error: {response.status} - {error_text}")
                    return False
    except Exception as e:
        logger.error(f"Failed to send admin message to bot: {e}")
        return False

async def send_sse_signal_to_bot(event_type, event_data):
    """Send SSE signal to bot via internal webhook"""
    try:
        import aiohttp

        bot_url = get_bot_webhook_url()
        async with aiohttp.ClientSession() as session:
            payload = {
                'event_type': event_type,
                'data': event_data
            }

            async with session.post(f"{bot_url}/sse_signal", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('success', False)
                else:
                    error_text = await response.text()
                    logger.error(f"Bot SSE signal error: {response.status} - {error_text}")
                    return False
    except Exception as e:
        logger.error(f"Failed to send SSE signal to bot: {e}")
        return False

# Global references for bot integration (avoid circular imports)
_bot_instance = None
_data_manager_instance = None

def set_bot_instance(bot):
    """Set global bot instance reference"""
    global _bot_instance
    _bot_instance = bot
    logger.info("Bot instance linked to backend")

    # Link bot instance to data_manager for Discord sync
    if data_manager:
        data_manager.set_bot_instance(bot)
        logger.info("Bot instance linked to data manager")

    # Also set bot instance on managers that need it
    if 'announcement_manager' in globals():
        announcement_manager.set_bot(bot)
        logger.info("Bot instance linked to announcement manager")

def set_data_manager(dm):
    """Set global data manager reference"""
    global _data_manager_instance
    _data_manager_instance = dm
    logger.info("Data manager linked to backend")

def run_backend():
    """Function for bot.py to start Flask backend in separate thread"""
    try:
        port = int(os.environ.get('PORT', 5000))
        logger.info(f"Starting Flask backend on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"Failed to start Flask backend: {e}")
        raise

# CORS after-request handler
@app.after_request
def after_request_cors(response):
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Type, X-Total-Count'
    return response

# OPTIONS handler
@app.route('/<path:path>', methods=['OPTIONS'])
@app.route('/api/<path:path>', methods=['OPTIONS'])
def handle_options(path=None):
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response = make_response('', 200)
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = request.headers.get(
            'Access-Control-Request-Headers',
            'Content-Type, Authorization, X-Requested-With'
        )
        response.headers['Access-Control-Max-Age'] = '3600'
        return response
    return make_response('Forbidden', 403)


# ========== HEALTH & SYSTEM ==========
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'environment': 'production' if IS_PRODUCTION else 'development',
        'cors_enabled': True
    })

@app.route('/api/bot/config', methods=['GET'])
def get_bot_config():
    """Get public bot configuration (client ID for invite link)"""
    return jsonify({
        'client_id': os.getenv('DISCORD_CLIENT_ID', ''),
        'bot_name': 'EvolvedLotus Bot'
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    bot_status = 'offline'
    uptime_str = '0d 0h 0m'
    server_count = 0
    
    if _bot_instance and _bot_instance.is_ready():
        bot_status = 'online'
        server_count = len(_bot_instance.guilds)
        
        # Calculate uptime
        if hasattr(_bot_instance, 'uptime'):
            delta = datetime.now(timezone.utc) - _bot_instance.uptime
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{days}d {hours}h {minutes}m"

    return jsonify({
        'bot_status': bot_status,
        'uptime': uptime_str,
        'servers': server_count
    })

# ========== AUTHENTICATION ==========
@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    """Login with username/password"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        # Check credentials using AuthManager
        user = auth_manager.authenticate_user(username, password)

        # Fallback: Check environment variables if AuthManager returns None
        if not user:
            env_username = os.getenv('ADMIN_USERNAME', 'admin')
            env_password = os.getenv('ADMIN_PASSWORD')
            
            if env_password and username == env_username and password == env_password:
                user = {
                    'id': 'admin-env-user',
                    'user_id': 'admin-env-user', # Maintain compatibility with different schemas
                    'username': username,
                    'is_superadmin': True,
                    'role': 'superadmin',
                    'permissions': ['read', 'write', 'delete', 'admin', 'superadmin']
                }
                logger.info(f"Login successful via Environment Variables for user: {username}")

        if not user:
            logger.warning(f"Failed login attempt for user: {username}")
            return jsonify({'error': 'Invalid username or password'}), 401

        # Create session
        # Pass the full user object to create_session (it expects user_data dict, not just ID)
        session_token = auth_manager.create_session(user)

        # Create response
        response = make_response(jsonify({
            'success': True,
            'user': user
        }))

        # Secure cookie settings
        secure_cookie = IS_PRODUCTION
        samesite = 'None' if IS_PRODUCTION else 'Lax'
        
        response.set_cookie(
            'session_token', 
            session_token, 
            httponly=True,
            secure=secure_cookie,
            samesite=samesite,
            max_age=86400  # 24 hours
        )
        
        logger.info(f"User logged in successfully: {username}")
        return response

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'An internal server error occurred'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True}), 200

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    """Get current authenticated user from session token"""
    session_token = request.cookies.get('session_token')
    
    if not session_token:
        return jsonify({'authenticated': False}), 401
    
    # Validate session
    user = auth_manager.validate_session(session_token)
    
    if not user:
        return jsonify({'authenticated': False}), 401
    
    return jsonify({
        'authenticated': True,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'is_superadmin': user.get('is_superadmin', False)
        }
    }), 200

@app.route('/api/auth/validate', methods=['GET'])
def validate_session():
    if session.get('authenticated'):
        return jsonify({'valid': True}), 200
    return jsonify({'valid': False}), 401

# CMS-compatible aliases
@app.route('/api/me', methods=['GET'])
def get_me():
    """Alias for /api/auth/me for CMS compatibility"""
    return get_current_user()


@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def login_alias():
    """Alias for /api/auth/login for CMS compatibility"""
    return login()

@app.route('/api/logout', methods=['POST'])
def logout_alias():
    """Alias for /api/auth/logout for CMS compatibility"""
    return logout()

# ========== DISCORD OAUTH2 AUTHENTICATION ==========
@app.route('/api/auth/discord/url', methods=['GET'])
def get_discord_auth_url():
    """Get Discord OAuth2 authorization URL"""
    try:
        # Generate CSRF state token
        import secrets
        state = secrets.token_urlsafe(32)
        
        # Store state in session for validation
        session['oauth_state'] = state
        
        auth_url = discord_oauth_manager.get_authorization_url(state)
        
        return jsonify({
            'success': True,
            'url': auth_url,
            'state': state
        }), 200
    except Exception as e:
        logger.error(f"Error generating Discord auth URL: {e}")
        return safe_error_response(e)

@app.route('/api/auth/discord/callback', methods=['POST'])
@limiter.limit("10 per minute")
def discord_oauth_callback():
    """Handle Discord OAuth2 callback"""
    try:
        data = request.json
        code = data.get('code')
        state = data.get('state')
        
        if not code:
            return jsonify({'success': False, 'error': 'Missing authorization code'}), 400
        
        # Validate state (CSRF protection)
        stored_state = session.get('oauth_state')
        if state and stored_state and state != stored_state:
            logger.warning(f"OAuth state mismatch: {state} != {stored_state}")
            return jsonify({'success': False, 'error': 'Invalid state parameter'}), 400
        
        # Clear state from session
        session.pop('oauth_state', None)
        
        # Authenticate user with Discord
        client_ip = get_remote_address()
        
        # Run async authentication
        if _bot_instance and _bot_instance.loop:
            future = asyncio.run_coroutine_threadsafe(
                discord_oauth_manager.authenticate_discord_user(code, client_ip),
                _bot_instance.loop
            )
            result = future.result(timeout=15)
        else:
            # Fallback for when bot is not connected
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    discord_oauth_manager.authenticate_discord_user(code, client_ip)
                )
            finally:
                loop.close()
        
        if not result:
            return jsonify({'success': False, 'error': 'Discord authentication failed'}), 500
        
        if result.get('error'):
            return jsonify({
                'success': False,
                'error': result.get('message', 'Authentication failed')
            }), 400
        
        # Set session cookie
        response = jsonify({
            'success': True,
            'user': {
                'id': result['user']['id'],
                'username': result['user']['username'],
                'discord_avatar': result['user'].get('discord_avatar'),
                'is_superadmin': False,
                'role': 'server_owner',
                'guilds': result.get('guilds', [])
            }
        })
        
        # Cookie settings
        cookie_kwargs = {
            'httponly': True,
            'secure': IS_PRODUCTION,
            'max_age': 86400   # 24 hours
        }
        
        if IS_PRODUCTION:
            cookie_kwargs['samesite'] = 'None'
        else:
            cookie_kwargs['samesite'] = 'Lax'
        
        response.set_cookie('session_token', result['session_token'], **cookie_kwargs)
        
        logger.info(f"✅ Discord OAuth login successful: {result['user']['username']}")
        
        return response
        
    except Exception as e:
        logger.exception(f"Discord OAuth callback error: {e}")
        return safe_error_response(e)

@app.route('/api/auth/discord/sync-guilds', methods=['POST'])
@require_auth
def sync_discord_guilds():
    """Re-sync user's Discord guild ownership"""
    try:
        user = request.user
        
        if user.get('login_type') != 'discord':
            return jsonify({'error': 'Only Discord users can sync guilds'}), 400
        
        # Run async guild sync
        if _bot_instance and _bot_instance.loop:
            future = asyncio.run_coroutine_threadsafe(
                discord_oauth_manager.sync_user_guilds(user['id']),
                _bot_instance.loop
            )
            success = future.result(timeout=10)
        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success = loop.run_until_complete(
                    discord_oauth_manager.sync_user_guilds(user['id'])
                )
            finally:
                loop.close()
        
        if success:
            return jsonify({'success': True, 'message': 'Guilds synced successfully'}), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to sync guilds'}), 500
            
    except Exception as e:
        logger.error(f"Error syncing Discord guilds: {e}")
        return safe_error_response(e)


# ========== SERVER MANAGEMENT ==========
@app.route('/api/servers', methods=['GET'])
@require_auth
def get_servers():
    try:
        user = request.user
        
        # Fetch all guilds with details from database
        result = data_manager.admin_client.table('guilds').select('*').execute()
        
        servers = []
        for guild in result.data:
            guild_id = guild['guild_id']
            
            # Filter based on user permissions
            # Superadmins see all servers
            if user.get('is_superadmin'):
                include_server = True
            # Discord OAuth users only see their allowed guilds
            elif user.get('allowed_guild_ids'):
                include_server = guild_id in user.get('allowed_guild_ids', [])
            else:
                # Fallback: include all (for backwards compatibility)
                include_server = True
            
            if include_server:
                servers.append({
                    'id': guild_id,
                    'name': guild['server_name'],
                    'member_count': guild['member_count'],
                    'icon_url': guild.get('icon_url'),
                    'is_active': guild.get('is_active', True)
                })
            
        return jsonify({'servers': servers}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/config', methods=['GET'])
@require_guild_access
def get_server_config(server_id):
    try:
        config = data_manager.load_guild_data(server_id, 'config')
        return jsonify(config), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/config', methods=['PUT'])
@require_guild_access
def update_server_config(server_id):
    try:
        data = request.get_json()
        
        # Load current config to merge with updates
        current_config = data_manager.load_guild_data(server_id, 'config')
        
        # Merge the updates into current config
        current_config.update(data)
        
        # Save merged config
        success = data_manager.save_guild_data(server_id, 'config', current_config)
        if success:
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Failed to update config'}), 500
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channels', methods=['GET'])
@require_guild_access
def get_channels(server_id):
    try:
        if _bot_instance:
            guild = _bot_instance.get_guild(int(server_id))
            if guild:
                channels = [
                    {'id': str(c.id), 'name': c.name, 'type': str(c.type), 'position': c.position} 
                    for c in guild.channels
                ]
                # Sort by position
                channels.sort(key=lambda x: x['position'])
                return jsonify({'channels': channels}), 200
        
        # Fallback if bot not ready or guild not found
        return jsonify({'channels': []}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/roles', methods=['GET'])
@require_guild_access
def get_roles(server_id):
    try:
        if _bot_instance:
            guild = _bot_instance.get_guild(int(server_id))
            if guild:
                roles = [
                    {'id': str(r.id), 'name': r.name, 'color': str(r.color), 'position': r.position} 
                    for r in guild.roles
                ]
                # Sort by position (reverse)
                roles.sort(key=lambda x: x['position'], reverse=True)
                return jsonify({'roles': roles}), 200
                
        return jsonify({'roles': []}), 200
    except Exception as e:
        return safe_error_response(e)

# ========== USER MANAGEMENT ==========
@app.route('/api/<server_id>/users', methods=['GET'])
@require_guild_access
def get_users(server_id):
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        users = data_manager.get_guild_users(server_id, page, limit)
        return jsonify(users), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/users/<user_id>', methods=['GET'])
@require_guild_access
def get_user(server_id, user_id):
    try:
        user = data_manager.get_user(server_id, user_id)
        return jsonify(user), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/users/<user_id>/balance', methods=['PUT'])
@require_guild_access
def update_balance(server_id, user_id):
    try:
        data = request.get_json()
        amount = data.get('amount', 0)
        transaction_manager.adjust_balance(server_id, user_id, amount, 'Admin adjustment')
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/users/<user_id>/roles', methods=['GET'])
@require_guild_access
def get_user_roles(server_id, user_id):
    """Get roles for a specific user in a guild"""
    try:
        if not _bot_instance or not _bot_instance.is_ready():
            return jsonify({'error': 'Bot is not ready'}), 503
        
        guild = _bot_instance.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404
        
        member = guild.get_member(int(user_id))
        if not member:
            return jsonify({'error': 'Member not found'}), 404
        
        # Get role IDs for this user
        role_ids = [str(role.id) for role in member.roles if role.id != guild.id]  # Exclude @everyone
        
        return jsonify({'roles': role_ids}), 200
    except Exception as e:
        logger.error(f"Error getting user roles: {e}")
        return safe_error_response(e)

@app.route('/api/<server_id>/users/<user_id>/roles', methods=['PUT'])
@require_guild_access
def update_user_roles(server_id, user_id):
    """Update roles for a specific user in a guild"""
    try:
        if not _bot_instance or not _bot_instance.is_ready():
            return jsonify({'error': 'Bot is not ready'}), 503
        
        data = request.get_json()
        role_ids = data.get('roles', [])
        
        guild = _bot_instance.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404
        
        member = guild.get_member(int(user_id))
        if not member:
            return jsonify({'error': 'Member not found'}), 404
        
        # Get role objects
        roles_to_add = []
        for role_id in role_ids:
            role = guild.get_role(int(role_id))
            if role:
                roles_to_add.append(role)
        
        # Update member roles (this is async, so we need to run it in the bot's event loop)
        async def update_roles():
            await member.edit(roles=roles_to_add, reason="Updated via CMS")
        
        asyncio.run_coroutine_threadsafe(update_roles(), _bot_instance.loop).result(timeout=10)
        
        return jsonify({'success': True}), 200
    except Exception as e:
        logger.error(f"Error updating user roles: {e}")
        return safe_error_response(e)

# ========== TASK MANAGEMENT ==========
@app.route('/api/<server_id>/tasks', methods=['GET'])
@require_guild_access
def get_tasks(server_id):
    try:
        tasks = task_manager.get_tasks(server_id)
        return jsonify({'tasks': tasks}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/tasks', methods=['POST'])
@require_guild_access
def create_task(server_id):
    try:
        data = request.get_json()

        # Check subscription tier limits
        config = data_manager.load_guild_data(server_id, 'config')
        tier = config.get('subscription_tier', 'free')
        
        # Get current task count
        current_tasks = task_manager.get_tasks(server_id)
        # Handle if get_tasks returns a dict (metadata wrapping tasks) or list
        if isinstance(current_tasks, dict) and 'tasks' in current_tasks:
             count = len(current_tasks['tasks'])
        elif isinstance(current_tasks, dict):
             count = len(current_tasks)
        elif isinstance(current_tasks, list):
             count = len(current_tasks)
        else:
             count = 0

        if not TierManager.check_limit(tier, 'max_tasks', count):
             limit = TierManager.get_limits(tier)["max_tasks"]
             return jsonify({'error': f'Free tier limit reached ({limit} tasks). Upgrade to Premium for unlimited tasks!'}), 403
        
        if _bot_instance and _bot_instance.loop:
            future = asyncio.run_coroutine_threadsafe(
                task_manager.create_task(server_id, data),
                _bot_instance.loop
            )
            task = future.result(timeout=10)
            return jsonify(task), 201
        else:
            # Fallback for when bot is not connected (e.g. unit tests)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                task = loop.run_until_complete(task_manager.create_task(server_id, data))
            finally:
                loop.close()
            return jsonify(task), 201
            
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/tasks/<task_id>', methods=['PUT'])
@require_guild_access
def update_task(server_id, task_id):
    try:
        data = request.get_json()
        
        if _bot_instance and _bot_instance.loop:
            future = asyncio.run_coroutine_threadsafe(
                task_manager.update_task(int(server_id), int(task_id), data),
                _bot_instance.loop
            )
            result = future.result(timeout=10)
            return jsonify(result), 200
        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(task_manager.update_task(int(server_id), int(task_id), data))
            finally:
                loop.close()
            return jsonify(result), 200
            
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/tasks/<task_id>', methods=['DELETE'])
@require_guild_access
def delete_task(server_id, task_id):
    try:
        if _bot_instance and _bot_instance.loop:
            future = asyncio.run_coroutine_threadsafe(
                task_manager.delete_task(int(server_id), int(task_id)),
                _bot_instance.loop
            )
            result = future.result(timeout=10)
        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(task_manager.delete_task(int(server_id), int(task_id)))
            finally:
                loop.close()
        
        if not result.get('success', False):
            return jsonify({'error': result.get('error', 'Failed to delete task')}), 400
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

# ========== SHOP MANAGEMENT ==========
@app.route('/api/<server_id>/shop', methods=['GET'])
@require_guild_access
def get_shop(server_id):
    try:
        items = shop_manager.get_items(server_id)
        return jsonify({'items': items}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/shop', methods=['POST'])
@require_guild_access
def create_shop_item(server_id):
    try:
        data = request.get_json()
        
        # Check subscription tier limits
        config = data_manager.load_guild_data(server_id, 'config')
        tier = config.get('subscription_tier', 'free')
        
        # Get current shop item count
        current_items = shop_manager.get_items(server_id)
        # Handle if get_items returns list or dict
        count = len(current_items) if isinstance(current_items, (list, dict)) else 0
        
        if not TierManager.check_limit(tier, 'max_shop_items', count):
             limit = TierManager.get_limits(tier)["max_shop_items"]
             return jsonify({'error': f'Free tier limit reached ({limit} items). Upgrade to Premium for unlimted items!'}), 403
        item = shop_manager.create_item(server_id, data)
        return jsonify(item), 201
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/shop/<item_id>', methods=['PUT'])
@require_guild_access
def update_shop_item(server_id, item_id):
    try:
        data = request.get_json()
        shop_manager.update_item(server_id, item_id, data)
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/shop/<item_id>', methods=['DELETE'])
@require_guild_access
def delete_shop_item(server_id, item_id):
    try:
        result = shop_manager.delete_item(int(server_id), str(item_id))
        if result:
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Item not found'}), 404
    except Exception as e:
        return safe_error_response(e)

# ========== TRANSACTIONS ==========
@app.route('/api/<server_id>/transactions', methods=['GET'])
@require_guild_access
def get_transactions(server_id):
    try:
        # Convert server_id to int as transaction_manager expects
        result = transaction_manager.get_transactions(int(server_id))
        # result is already a dict with 'transactions', 'total', 'has_more'
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting transactions for guild {server_id}: {e}")
        return safe_error_response(e)

# ========== ANNOUNCEMENTS ==========
@app.route('/api/<server_id>/announcements', methods=['GET'])
@require_guild_access
def get_announcements(server_id):
    try:
        announcements = announcement_manager.get_announcements(server_id)
        return jsonify({'announcements': announcements}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/announcements', methods=['POST'])
@require_guild_access
def create_announcement(server_id):
    try:
        data = request.get_json()
        
        # Extract required parameters
        title = data.get('title')
        content = data.get('content')
        channel_id = data.get('channel_id')
        
        # Get author info from session
        user = request.user
        author_id = user.get('id', 'admin-env-user')
        author_name = user.get('username', 'Admin')
        
        # Optional parameters
        announcement_type = data.get('type', 'general')
        embed_color = data.get('embed_color', '#5865F2')
        auto_pin = data.get('pinned', False)
        
        # Use bot loop for async operations
        if _bot_instance and _bot_instance.loop:
            future = asyncio.run_coroutine_threadsafe(
                announcement_manager.create_announcement(
                    guild_id=server_id,
                    title=title,
                    content=content,
                    channel_id=channel_id,
                    author_id=author_id,
                    author_name=author_name,
                    announcement_type=announcement_type,
                    embed_color=embed_color,
                    auto_pin=auto_pin
                ),
                _bot_instance.loop
            )
            announcement = future.result(timeout=10)
            return jsonify(announcement), 201
        else:
            return jsonify({'error': 'Bot is not ready'}), 503
            
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/\u003cserver_id\u003e/announcements/\u003cannouncement_id\u003e', methods=['GET'])
@require_guild_access
def get_announcement(server_id, announcement_id):
    try:
        result = data_manager.admin_client.table('announcements') \
            .select('*') \
            .eq('announcement_id', announcement_id) \
            .eq('guild_id', str(server_id)) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            return jsonify({'error': 'Announcement not found'}), 404
        
        return jsonify({'announcement': result.data[0]}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/\u003cserver_id\u003e/announcements/\u003cannouncement_id\u003e', methods=['PUT'])
@require_guild_access
def update_announcement(server_id, announcement_id):
    try:
        data = request.get_json()
        
        # Update announcement in database
        update_data = {}
        if 'title' in data:
            update_data['title'] = data['title']
        if 'content' in data:
            update_data['content'] = data['content']
        if 'channel_id' in data:
            update_data['channel_id'] = data['channel_id']
        if 'is_pinned' in data:
            update_data['is_pinned'] = data['is_pinned']
        
        result = data_manager.admin_client.table('announcements') \
            .update(update_data) \
            .eq('announcement_id', announcement_id) \
            .eq('guild_id', str(server_id)) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            return jsonify({'error': 'Announcement not found'}), 404
        
        return jsonify({'success': True, 'announcement': result.data[0]}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/\u003cserver_id\u003e/announcements/\u003cannouncement_id\u003e', methods=['DELETE'])
@require_guild_access
def delete_announcement(server_id, announcement_id):
    try:
        result = data_manager.admin_client.table('announcements') \
            .delete() \
            .eq('announcement_id', announcement_id) \
            .eq('guild_id', str(server_id)) \
            .execute()
        
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

# ========== EMBEDS ==========
@app.route('/api/<server_id>/embeds', methods=['GET'])
@require_guild_access
def get_embeds(server_id):
    try:
        embeds = embed_manager.get_embeds(server_id)
        return jsonify({'embeds': embeds}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/embeds', methods=['POST'])
@require_guild_access
def create_embed(server_id):
    try:
        data = request.get_json()
        embed_data = embed_builder.create_embed(server_id, data)
        
        # Save to database
        # Prepare JSONB fields
        footer_data = {'text': embed_data.get('footer')} if embed_data.get('footer') else None
        thumbnail_data = {'url': embed_data.get('thumbnail_url')} if embed_data.get('thumbnail_url') else None
        image_data = {'url': embed_data.get('image_url')} if embed_data.get('image_url') else None

        data_manager.admin_client.table('embeds').upsert({
            'embed_id': embed_data['embed_id'],
            'guild_id': str(server_id),
            'title': embed_data.get('title'),
            'description': embed_data.get('description'),
            'color': embed_data.get('color'),
            'fields': embed_data.get('fields', []),
            'footer': footer_data,
            'thumbnail': thumbnail_data,
            'image': image_data,
            'channel_id': embed_data.get('channel_id'),
            'created_by': request.user.get('id', 'unknown'),
            'created_at': embed_data['created_at']
        }).execute()
        
        return jsonify(embed_data), 201
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/embeds/<embed_id>', methods=['GET'])
@require_guild_access
def get_embed(server_id, embed_id):
    try:
        embed = embed_builder.get_embed(server_id, embed_id)
        return jsonify(embed), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/embeds/<embed_id>', methods=['PUT'])
@require_guild_access
def update_embed(server_id, embed_id):
    try:
        data = request.get_json()
        embed = embed_builder.update_embed(server_id, embed_id, data)
        return jsonify(embed), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/embeds/<embed_id>', methods=['DELETE'])
@require_guild_access
def delete_embed(server_id, embed_id):
    try:
        embed_builder.delete_embed(server_id, embed_id)
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/embeds/<embed_id>/send', methods=['POST'])
@require_guild_access
def send_embed_to_channel(server_id, embed_id):
    """Send an embed to a specific channel"""
    try:
        data = request.get_json()
        channel_id = data.get('channel_id')
        
        if not channel_id:
            return jsonify({'error': 'channel_id is required'}), 400
        
        if not _bot_instance or not _bot_instance.is_ready():
            return jsonify({'error': 'Bot is not ready'}), 503
        
        # Get the embed data from database
        result = data_manager.admin_client.table('embeds') \
            .select('*') \
            .eq('embed_id', embed_id) \
            .eq('guild_id', str(server_id)) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            return jsonify({'error': 'Embed not found'}), 404
        
        embed_data = result.data[0]
        
        # Get the channel
        guild = _bot_instance.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404
        
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return jsonify({'error': 'Channel not found'}), 404
        
        # Build the Discord embed
        embed = discord.Embed(
            title=embed_data.get('title'),
            description=embed_data.get('description'),
            color=int(embed_data.get('color', '0x5865F2').replace('#', '0x'), 16) if embed_data.get('color') else 0x5865F2
        )
        
        if embed_data.get('footer'):
            embed.set_footer(text=embed_data['footer'])
        
        if embed_data.get('thumbnail'):
            embed.set_thumbnail(url=embed_data['thumbnail'])
        
        if embed_data.get('image'):
            embed.set_image(url=embed_data['image'])
        
        # Add fields if present
        if embed_data.get('fields'):
            for field in embed_data['fields']:
                embed.add_field(
                    name=field.get('name', 'Field'),
                    value=field.get('value', 'Value'),
                    inline=field.get('inline', False)
                )
        
        # Send the embed
        async def send_message():
            await channel.send(embed=embed)
        
        asyncio.run_coroutine_threadsafe(send_message(), _bot_instance.loop).result(timeout=10)
        
        logger.info(f"Embed {embed_id} sent to channel {channel_id} in guild {server_id}")
        return jsonify({'success': True, 'message': 'Embed sent successfully'}), 200
        
    except Exception as e:
        logger.error(f"Error sending embed: {e}")
        return safe_error_response(e)

@app.route('/api/<server_id>/logs', methods=['GET'])
@require_guild_access
def get_logs(server_id):
    try:
        # Fetch moderation audit logs from database
        limit = int(request.args.get('limit', 100))
        log_type = request.args.get('type', '')
        
        result = data_manager.admin_client.table('moderation_audit_logs') \
            .select('*') \
            .eq('guild_id', server_id) \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()
        
        logs = result.data if result.data else []
        
        # Filter by type if specified
        if log_type:
            logs = [log for log in logs if log.get('action', '').startswith(log_type)]
        
        return jsonify({'logs': logs}), 200
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/<server_id>/bot_status', methods=['POST'])
@require_guild_access
def update_bot_status(server_id):
    try:
        data = request.get_json()
        # Validate data
        status_message = data.get('message')
        status_type = data.get('type', 'playing')

        # Load current config
        current_config = data_manager.load_guild_data(server_id, 'config')

        # Update fields
        current_config['bot_status_message'] = status_message
        current_config['bot_status_type'] = status_type

        # Save config (file-based)
        data_manager.save_guild_data(server_id, 'config', current_config)
        
        # ALSO save to Supabase guilds table (for persistence across restarts)
        try:
            data_manager.supabase.table('guilds').update({
                'bot_status_message': status_message,
                'bot_status_type': status_type
            }).eq('guild_id', server_id).execute()
            logger.info(f"Saved bot status to Supabase for guild {server_id}")
        except Exception as e:
            logger.error(f"Failed to save bot status to Supabase: {e}")
            # Continue anyway - at least file-based config is saved

        # If bot is running, update presence immediately
        if _bot_instance and _bot_instance.is_ready():
            try:
                activity = None
                if status_type == 'playing':
                    activity = discord.Game(name=status_message)
                elif status_type == 'watching':
                    activity = discord.Activity(type=discord.ActivityType.watching, name=status_message)
                elif status_type == 'listening':
                    activity = discord.Activity(type=discord.ActivityType.listening, name=status_message)
                elif status_type == 'competing':
                    activity = discord.Activity(type=discord.ActivityType.competing, name=status_message)
                elif status_type == 'streaming':
                    url = data.get('streaming_url')
                    activity = discord.Streaming(name=status_message, url=url)

                status = discord.Status.online
                presence_str = data.get('presence', 'online')
                if presence_str == 'idle':
                    status = discord.Status.idle
                elif presence_str == 'dnd':
                    status = discord.Status.dnd
                elif presence_str == 'invisible':
                    status = discord.Status.invisible

                asyncio.run_coroutine_threadsafe(
                    _bot_instance.change_presence(activity=activity, status=status),
                    _bot_instance.loop
                )
                logger.info(f"Updated bot presence to {status_type}: {status_message}")
            except Exception as e:
                logger.error(f"Failed to update bot presence: {e}")
                # Don't fail the request if just the live update fails


        return jsonify({'success': True, 'message': 'Bot status updated'}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/messages/<channel_id>/<message_id>', methods=['GET'])
@require_guild_access
def get_discord_message(server_id, channel_id, message_id):
    """Fetch a message from Discord to extract its content/embeds"""
    try:
        if not _bot_instance:
            return jsonify({'error': 'Bot instance not available'}), 503
            
        async def fetch_message():
            guild = _bot_instance.get_guild(int(server_id))
            if not guild:
                return {'error': 'Guild not found'}, 404
                
            channel = guild.get_channel(int(channel_id))
            if not channel:
                return {'error': 'Channel not found'}, 404
                
            try:
                message = await channel.fetch_message(int(message_id))
                
                # Format embeds for frontend
                embeds = []
                for embed in message.embeds:
                    embed_dict = {
                        'title': embed.title,
                        'description': embed.description,
                        'color': embed.color.value if embed.color else None,
                        'fields': [{'name': f.name, 'value': f.value, 'inline': f.inline} for f in embed.fields],
                        'footer': {'text': embed.footer.text, 'icon_url': embed.footer.icon_url} if embed.footer else None,
                        'image': {'url': embed.image.url} if embed.image else None,
                        'thumbnail': {'url': embed.thumbnail.url} if embed.thumbnail else None,
                        'author': {'name': embed.author.name, 'url': embed.author.url, 'icon_url': embed.author.icon_url} if embed.author else None
                    }
                    embeds.append(embed_dict)
                    
                return {
                    'id': str(message.id),
                    'content': message.content,
                    'author': {
                        'id': str(message.author.id),
                        'username': message.author.name,
                        'avatar': str(message.author.display_avatar.url) if message.author.display_avatar else None
                    },
                    'embeds': embeds,
                    'created_at': message.created_at.isoformat()
                }, 200
            except Exception as e:
                logger.error(f"Error fetching message {message_id}: {e}")
                return {'error': f'Failed to fetch message: {str(e)}'}, 404

        # Run async function in bot's loop
        import asyncio
        future = asyncio.run_coroutine_threadsafe(fetch_message(), _bot_instance.loop)
        result, status = future.result(timeout=10)
        
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Error in get_discord_message: {e}")
        return safe_error_response(e)

@app.route('/api/<server_id>/messages/<channel_id>/<message_id>', methods=['PATCH', 'PUT'])
@require_guild_access
def edit_discord_message(server_id, channel_id, message_id):
    """Edit an existing message in Discord"""
    try:
        if not _bot_instance:
            return jsonify({'error': 'Bot instance not available'}), 503
            
        data = request.get_json()
        
        async def edit_message():
            guild = _bot_instance.get_guild(int(server_id))
            if not guild:
                return {'error': 'Guild not found'}, 404
                
            channel = guild.get_channel(int(channel_id))
            if not channel:
                return {'error': 'Channel not found'}, 404
                
            try:
                message = await channel.fetch_message(int(message_id))
                
                # Format embed from data
                import discord
                # Handle possible color formats
                color_val = data.get('color', '#5865F2')
                if isinstance(color_val, str) and color_val.startswith('#'):
                    color_int = int(color_val.strip('#'), 16)
                else:
                    color_int = int(color_val) if color_val else 0x5865F2

                embed = discord.Embed(
                    title=data.get('title'),
                    description=data.get('description'),
                    color=color_int
                )
                
                if data.get('footer'):
                    footer_text = data['footer']
                    if isinstance(footer_text, dict):
                        footer_text = footer_text.get('text', '')
                    embed.set_footer(text=footer_text)
                if data.get('image_url'):
                    embed.set_image(url=data.get('image_url'))
                if data.get('thumbnail_url'):
                    embed.set_thumbnail(url=data.get('thumbnail_url'))
                    
                await message.edit(embed=embed)
                return {'success': True, 'message': 'Message edited successfully'}, 200
            except Exception as e:
                logger.error(f"Error editing message {message_id}: {e}")
                return {'error': f'Failed to edit message: {str(e)}'}, 404

        # Run async function in bot's loop
        import asyncio
        future = asyncio.run_coroutine_threadsafe(edit_message(), _bot_instance.loop)
        result, status = future.result(timeout=10)
        
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Error in edit_discord_message: {e}")
        return safe_error_response(e)

# ========== MODERATION ENDPOINTS ==========
@app.route('/api/<server_id>/admin/cache/clear', methods=['POST'])
@require_guild_access
def clear_cache(server_id):
    """Clear all caches for the guild"""
    try:
        # Clear the data manager cache
        data_manager.invalidate_cache(server_id)
        
        # If cache manager exists, clear its caches too
        if 'cache_manager' in globals():
            cache_manager.clear_guild_cache(server_id)
        
        logger.info(f"Cache cleared for guild {server_id}")
        return jsonify({'success': True, 'message': 'Cache cleared successfully'}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/admin/sync', methods=['POST'])
@require_guild_access
def sync_data(server_id):
    """Sync guild data with Discord"""
    try:
        # Trigger sync operations
        if sync_manager:
            result = sync_manager.sync_guild_data(server_id)
            return jsonify(result), 200
        else:
            # Fallback manual sync
            config = data_manager.load_guild_data(server_id, 'config', force_reload=True)
            currency = data_manager.load_guild_data(server_id, 'currency', force_reload=True)
            tasks = data_manager.load_guild_data(server_id, 'tasks', force_reload=True)
            
            return jsonify({
                'success': True, 
                'message': 'Data synced manually',
                'data_reloaded': ['config', 'currency', 'tasks']
            }), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/admin/validate', methods=['POST'])
@require_guild_access
def validate_integrity(server_id):
    """Validate guild data integrity"""
    try:
        issues = []
        
        # Check currency data integrity
        try:
            currency_data = data_manager.load_guild_data(server_id, 'currency')
            total_balance = sum(user.get('balance', 0) for user in currency_data.get('users', {}).values())
            
            # Check balance matches metadata
            metadata_total = currency_data.get('metadata', {}).get('total_currency', 0)
            if abs(total_balance - metadata_total) > 0.01:  # Small tolerance for floating point
                issues.append({
                    'issue': 'Balance mismatch',
                    'details': f'Calculated total: {total_balance}, Stored total: {metadata_total}',
                    'severity': 'medium'
                })
        except Exception as e:
            issues.append({
                'issue': 'Currency data error',
                'details': str(e),
                'severity': 'high'
            })
        
        # Check for orphaned user tasks (tasks claimed by users that don't exist)
        try:
            currency_data = data_manager.load_guild_data(server_id, 'currency')
            tasks_data = data_manager.load_guild_data(server_id, 'tasks')
            
            existing_user_ids = set(currency_data.get('users', {}).keys())
            task_user_ids = set()
            
            for task_id, task in tasks_data.get('user_tasks', {}).items():
                task_user_ids.update(task.keys())
            
            orphaned_users = task_user_ids - existing_user_ids
            if orphaned_users:
                issues.append({
                    'issue': 'Orphaned user tasks',
                    'details': f'Tasks claimed by {len(orphaned_users)} non-existent users',
                    'severity': 'low'
                })
        except Exception as e:
            issues.append({
                'issue': 'Task validation error',
                'details': str(e),
                'severity': 'medium'
            })
        
        severity_counts = {'low': 0, 'medium': 0, 'high': 0}
        for issue in issues:
            severity_counts[issue['severity']] += 1
        
        return jsonify({
            'success': True,
            'validation_complete': True,
            'issues_found': len(issues),
            'severity_breakdown': severity_counts,
            'issues': issues,
            'recommendations': [
                'Regular validation helps catch data inconsistencies early',
                'Consider cleaning orphaned records periodically'
            ] if issues else []
        }), 200
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/admin/moderation/strikes', methods=['GET'])
@require_guild_access
def get_strikes(server_id):
    """Get user strike/warning data"""
    try:
        # For now, return placeholder data since we don't have a strikes system implemented
        # This could be extended to store strikes in the database
        
        return jsonify({
            'success': True,
            'strikes': [],
            'message': 'Strike system not yet implemented',
            'note': 'This would track user violations and automated actions'
        }), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/admin/moderation/jobs', methods=['GET'])
@require_guild_access
def get_scheduled_jobs(server_id):
    """Get scheduled moderation jobs"""
    try:
        # For now, return placeholder data since we don't have scheduled jobs implemented
        # This could be extended to support automated moderation tasks
        
        return jsonify({
            'success': True,
            'jobs': [
                {
                    'id': 'temp_ban_cleanup',
                    'name': 'Temporary Ban Cleanup',
                    'description': 'Remove expired temporary bans',
                    'enabled': True,
                    'schedule': 'Every 5 minutes',
                    'last_run': None,
                    'next_run': 'Now',
                    'status': 'ready'
                },
                {
                    'id': 'inactive_channel_cleanup',
                    'name': 'Inactive Channel Cleanup', 
                    'description': 'Archive channels without recent activity',
                    'enabled': False,
                    'schedule': 'Daily at 3 AM',
                    'last_run': None,
                    'next_run': '2025-11-21 03:00:00',
                    'status': 'disabled'
                }
            ],
            'message': 'Scheduled jobs system ready for implementation'
        }), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/admin/permissions/channels', methods=['POST'])
@require_guild_access
def configure_channel_permissions(server_id):
    """Configure bot permissions for specific channels"""
    try:
        data = request.get_json()
        channel_configs = data.get('channel_configs', {})
        
        # Load current config
        config = data_manager.load_guild_data(server_id, 'config')
        
        # Update channel permissions
        if 'channel_permissions' not in config:
            config['channel_permissions'] = {}
            
        config['channel_permissions'].update(channel_configs)
        
        # Save config
        data_manager.save_guild_data(server_id, 'config', config)
        
        return jsonify({
            'success': True, 
            'message': f'Updated permissions for {len(channel_configs)} channels'
        }), 200
    except Exception as e:
        return safe_error_response(e)

# ========== SERVER-SENT EVENTS (SSE) ==========
@app.route('/api/sse/<guild_id>')
@require_auth
def sse_stream(guild_id):
    """Server-Sent Events stream with guild isolation"""

    # Validate user has access to this guild
    user_guilds = data_manager.get_user_guilds(request.user['id'])
    if guild_id not in [g['guild_id'] for g in user_guilds]:
        return jsonify({'error': 'Access denied'}), 403

    def generate():
        import uuid
        client_id = str(uuid.uuid4())

        # Register client with guild filter
        sse_manager.register_client(client_id, guild_id)

        try:
            # Send initial connection event
            yield f"data: {json.dumps({'type': 'connected', 'client_id': client_id})}\n\n"

            last_event_time = datetime.now()
            while True:
                # Get events for this guild only
                events = sse_manager.get_client_events(client_id, guild_id)

                for event in events:
                    # Double-check guild_id matches (security)
                    if event.get('guild_id') == guild_id:
                        yield f"data: {json.dumps(event)}\n\n"

                # Send keepalive every 30 seconds
                if datetime.now() - last_event_time > timedelta(seconds=30):
                    yield f": keepalive\n\n"
                    last_event_time = datetime.now()

                import time
                time.sleep(1)

        except GeneratorExit:
            # Client disconnected
            sse_manager.unregister_client(client_id)

    from flask import Response
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/stream', methods=['GET'])
def stream():
    """Server-Sent Events endpoint for real-time updates"""
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    def generate():
        """Generator function for SSE stream"""
        client_id = request.args.get('client_id', f"web_{id(request)}")
        subscriptions = request.args.get('subscriptions', 'balance_update,task_update,shop_update,user_update').split(',')

        # Register client with SSE manager
        metadata = {
            'user_agent': request.headers.get('User-Agent', 'Unknown'),
            'ip': request.remote_addr,
            'session_id': session.get('username', 'anonymous')
        }

        if not sse_manager.register_client(client_id, subscriptions, metadata):
            yield "data: {\"error\": \"Failed to register client\"}\n\n"
            return

        try:
            logger.info(f"SSE client {client_id} connected with subscriptions: {subscriptions}")

            # Send initial connection confirmation
            yield f"data: {{\"type\": \"connected\", \"client_id\": \"{client_id}\", \"subscriptions\": {subscriptions}}}\n\n"

            # Get client's event queue
            event_queue = sse_manager.get_client_events(client_id)
            if not event_queue:
                yield "data: {\"error\": \"No event queue available\"}\n\n"
                return

            # Use synchronous waiting instead of asyncio.run()
            import time
            while True:
                try:
                    # Check for events without blocking indefinitely
                    # This is a simplified synchronous approach
                    if hasattr(event_queue, '_get_nowait'):
                        try:
                            event = event_queue._get_nowait()
                        except:
                            # No event available, send keepalive and continue
                            yield "data: {\"type\": \"keepalive\", \"timestamp\": \"" + datetime.utcnow().isoformat() + "Z\"}\n\n"
                            time.sleep(1)  # Brief pause to prevent busy waiting
                            continue
                    else:
                        # Fallback keepalive
                        yield "data: {\"type\": \"keepalive\", \"timestamp\": \"" + datetime.utcnow().isoformat() + "Z\"}\n\n"
                        time.sleep(1)
                        continue

                    # Format as SSE
                    event_json = json.dumps(event)
                    yield f"data: {event_json}\n\n"

                except Exception as e:
                    logger.error(f"SSE stream error for client {client_id}: {e}")
                    break

        except GeneratorExit:
            logger.info(f"SSE client {client_id} disconnected")
        except Exception as e:
            logger.error(f"SSE stream error for client {client_id}: {e}")
        finally:
            # Unregister client
            sse_manager.unregister_client(client_id)

    # Return SSE response
    origin = request.headers.get('Origin')
    response = app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        }
    )

    # Set CORS headers manually for SSE (Flask-CORS doesn't handle streaming responses)
    if origin and origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'

    return response

@app.route('/api/stream/test', methods=['POST'])
def test_stream():
    """Test SSE functionality"""
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
        event_type = data.get('event_type', 'test')
        event_data = data.get('data', {'message': 'Test event'})

        # Broadcast test event
        sse_manager.broadcast_event(event_type, event_data)

        return jsonify({'success': True, 'message': f'Test event "{event_type}" broadcasted'}), 200
    except Exception as e:
        return safe_error_response(e)

# ========== AD CLAIM SYSTEM (PERMANENT GLOBAL TASK) ==========
@app.route('/api/<server_id>/ad-claim/create-session', methods=['POST'])
@require_guild_access
def create_ad_session(server_id):
    """Create a new ad viewing session for a user"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Missing user_id'}), 400
        
        # Get client info for fraud prevention
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent')
        
        # Create ad session
        result = ad_claim_manager.create_ad_session(
            user_id=user_id,
            guild_id=server_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        return jsonify(result), 201
        
    except Exception as e:
        return safe_error_response(e)


@app.route('/api/<server_id>/ad-claim/stats/<user_id>', methods=['GET'])
@require_guild_access
def get_ad_stats(server_id, user_id):
    """Get ad viewing statistics for a user"""
    try:
        result = ad_claim_manager.get_user_ad_stats(user_id, server_id)
        return jsonify(result), 200
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/ad-claim/session/<session_id>', methods=['GET'])
def get_ad_session(session_id):
    """Get ad session details for the viewer"""
    try:
        # Fetch from database via ad_claim_manager
        result = data_manager.admin_client.table('ad_views') \
            .select('*') \
            .eq('ad_session_id', session_id) \
            .execute()
            
        if not result.data:
            return jsonify({'error': 'Session not found'}), 404
            
        ad_view = result.data[0]
        
        # Format response
        response = {
            'session_id': ad_view['ad_session_id'],
            'ad_type': ad_view['ad_type'],
            'reward_amount': ad_view['reward_amount'],
            'is_verified': ad_view['is_verified'],
            'custom_ad': ad_view.get('metadata', {}).get('custom_ad')
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error fetching ad session {session_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/global-tasks', methods=['GET'])
def get_global_tasks():
    """Get all active global tasks (including ad claim task)"""
    try:
        tasks = ad_claim_manager.get_all_global_tasks()
        return jsonify({'tasks': tasks}), 200
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/global-tasks/<task_key>', methods=['GET'])
def get_global_task(task_key):
    """Get a specific global task by key"""
    try:
        task = ad_claim_manager.get_global_task(task_key)
        
        if task:
            return jsonify(task), 200
        else:
            return jsonify({'error': 'Task not found'}), 404
            
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/monetag/postback', methods=['POST'])
def monetag_postback():
    """Handle Monetag ad view postback"""
    try:
        data = request.get_json() or request.form.to_dict()
        
        logger.info(f"Received Monetag postback: {data}")
        
        # Process the postback
        result = ad_claim_manager.handle_monetag_postback(data)
        
        # Monetag expects a 200 OK response
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error processing Monetag postback: {e}")
        # Still return 200 to Monetag to prevent retries
        return jsonify({'success': False, 'error': str(e)}), 200

# ========== AD CLAIM ENDPOINTS ==========
@app.route('/api/ad-claim/verify', methods=['POST'])
def verify_ad_claim():
    """Verify an ad view and grant reward"""
    try:
        data = request.json
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Session ID is required'
            }), 400
        
        # Use ad_claim_manager to verify the ad view
        result = ad_claim_manager.verify_ad_view(session_id)
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'verified': True,
                'reward_amount': result.get('reward_amount', 10),
                'new_balance': result.get('new_balance', 0),
                'transaction_id': result.get('transaction_id')
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Verification failed')
            }), 400
            
    except Exception as e:
        logger.error(f"Error verifying ad claim: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'An error occurred while verifying the ad view'
        }), 500


# ========== STATIC FILES ==========
@app.route('/')
def serve_dashboard():
    return send_from_directory('docs', 'index.html')

@app.route('/script.js')
def serve_script():
    return send_from_directory('docs', 'app.js')

@app.route('/styles.css')
def serve_styles():
    return send_from_directory('docs', 'styles.css')

@app.route('/favicon.ico')
def serve_favicon():
    return '', 204

# ========== ADMIN SERVER MANAGEMENT ==========
@app.route('/api/admin/servers/<server_id>/leave', methods=['POST'])
@require_auth
def leave_server(server_id):
    """Allow super admins to make the bot leave a server"""
    try:
        user = request.user
        
        # Only super admins can use this endpoint
        if not user.get('is_superadmin'):
            return jsonify({'error': 'Unauthorized. Super admin access required.'}), 403
        
        if not _bot_instance or not _bot_instance.is_ready():
            return jsonify({'error': 'Bot is not ready'}), 503
        
        # Get the guild
        guild = _bot_instance.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Server not found or bot is not in this server'}), 404
        
        guild_name = guild.name
        
        # Leave the guild (async operation)
        async def leave_guild():
            await guild.leave()
            logger.info(f"Bot left server: {guild_name} ({server_id}) - Requested by admin: {user.get('username')}")
        
        # Run the async operation
        if _bot_instance.loop:
            future = asyncio.run_coroutine_threadsafe(leave_guild(), _bot_instance.loop)
            future.result(timeout=10)
        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(leave_guild())
            finally:
                loop.close()
        
        # Update database to mark guild as inactive
        try:
            data_manager.admin_client.table('guilds').update({
                'is_active': False,
                'left_at': datetime.now(timezone.utc).isoformat()
            }).eq('guild_id', server_id).execute()
        except Exception as db_error:
            logger.warning(f"Failed to update guild status in database: {db_error}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully left server: {guild_name}'
        }), 200
        
    except Exception as e:
        logger.error(f"Error leaving server {server_id}: {e}")
        return safe_error_response(e)

# ========== ERROR HANDLERS ==========
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal error: {e}")
    return jsonify({'error': 'Internal server error'}), 500

# ========== STARTUP ==========
def run_backend():
    """Run the Flask app (called from railway_start.py)"""
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask on 0.0.0.0:{port}")
    # Disable debug mode and reloader to prevent main thread issues
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ========== STARTUP ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
