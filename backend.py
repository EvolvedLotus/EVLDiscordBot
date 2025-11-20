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
app = Flask(__name__, static_folder='web', static_url_path='')

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
        if user['session_expires'] - datetime.now(timezone.utc) < timedelta(hours=1):
            # Refresh session
            new_expires = datetime.now(timezone.utc) + timedelta(hours=24)
            auth_manager.refresh_session(session_token, new_expires)

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

        # Validate user has access to this guild
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

    # Initialize managers
    data_manager = DataManager()
    cache_manager = CacheManager()
    audit_manager = AuditManager(data_manager)
    auth_manager = AuthManager(data_manager, os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-change-me'))
    transaction_manager = TransactionManager(data_manager, audit_manager, cache_manager)
    task_manager = TaskManager(data_manager, transaction_manager)
    shop_manager = ShopManager(data_manager, transaction_manager)
    announcement_manager = AnnouncementManager(data_manager)
    embed_builder = EmbedBuilder()
    embed_manager = EmbedManager(data_manager)
    sync_manager = SyncManager(data_manager, audit_manager, sse_manager)

    logger.info("✅ All managers initialized")
except ImportError as e:
    logger.warning(f"⚠️  Some managers not available: {e}")

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
@limiter.limit("5 per minute")  # Max 5 login attempts per minute per IP
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'success': False, 'error': 'Missing credentials'}), 400

    client_ip = get_remote_address()
    user = None

    # 1. Check Environment Variables (Simple Mode) - PRIORITY
    env_password = os.getenv('ADMIN_PASSWORD')
    env_username = os.getenv('ADMIN_USERNAME', 'admin')

    if env_password:
        if username == env_username and password == env_password:
            user = {
                'id': 'admin-env-user',
                'username': username,
                'is_superadmin': True,
                'role': 'superadmin',
                'permissions': ['read', 'write', 'delete', 'admin', 'superadmin'],
                'session_expires': datetime.now(timezone.utc) + timedelta(hours=24) # Helper for require_auth
            }
            logger.info(f"Login successful via Environment Variables for user: {username}")
        else:
            logger.warning(f"Failed env var login attempt for {username} from {client_ip}")
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    else:
        # 2. Database Mode (Fallback)
        try:
            # Check for account lockout
            if client_ip in failed_login_attempts:
                recent_failures = [
                    (ts, u) for ts, u in failed_login_attempts[client_ip]
                    if datetime.now() - ts < timedelta(minutes=15)
                ]
                failed_login_attempts[client_ip] = recent_failures

                if len(recent_failures) >= 5:
                    logger.warning(f"Account lockout triggered for IP: {client_ip}")
                    return jsonify({
                        'success': False,
                        'error': 'Too many failed attempts. Try again in 15 minutes.'
                    }), 429

            # Authenticate against DB
            user = auth_manager.authenticate_user(username, password)

            if not user:
                # Log failed attempt
                if client_ip not in failed_login_attempts:
                    failed_login_attempts[client_ip] = []
                failed_login_attempts[client_ip].append((datetime.now(), username))

                logger.warning(f"Failed DB login attempt for {username} from {client_ip}")
                return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

            # Clear failed attempts
            if client_ip in failed_login_attempts:
                del failed_login_attempts[client_ip]
                
        except Exception as e:
            logger.exception(f"DB Login error: {e}")
            return jsonify({'success': False, 'error': 'Server error'}), 500

    try:
        # Create session (Fix: Use correct signature for AuthManager)
        # AuthManager.create_session(user_data) -> session_id
        session_token = auth_manager.create_session(user)

        # Update last_login if it's a DB user (optional, skip for env user)
        if user.get('id') != 'admin-env-user':
            auth_manager.update_last_login(user['id'])

        response = jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'is_superadmin': user.get('is_superadmin', False)
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

        response.set_cookie('session_token', session_token, **cookie_kwargs)

        return response

    except Exception as e:
        logger.exception(f"Session creation error: {e}")
        return jsonify({'success': False, 'error': 'Server error'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True}), 200

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    if session.get('authenticated'):
        return jsonify({
            'authenticated': True,
            'user': {'username': session.get('username')}
        }), 200
    return jsonify({'authenticated': False}), 401

@app.route('/api/auth/validate', methods=['GET'])
def validate_session():
    if session.get('authenticated'):
        return jsonify({'valid': True}), 200
    return jsonify({'valid': False}), 401

# ========== SERVER MANAGEMENT ==========
@app.route('/api/servers', methods=['GET'])
@require_auth
def get_servers():
    try:
        # Fetch all guilds with details from database
        result = data_manager.admin_client.table('guilds').select('*').execute()
        
        servers = []
        for guild in result.data:
            servers.append({
                'id': guild['guild_id'],
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
        config = data_manager.get_guild_config(server_id)
        return jsonify(config), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/config', methods=['PUT'])
@require_guild_access
def update_server_config(server_id):
    try:
        data = request.get_json()
        data_manager.update_guild_config(server_id, data)
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channels', methods=['GET'])
@require_guild_access
def get_channels(server_id):
    try:
        channels = data_manager.get_guild_channels(server_id)
        return jsonify({'channels': channels}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/roles', methods=['GET'])
@require_guild_access
def get_roles(server_id):
    try:
        roles = data_manager.get_guild_roles(server_id)
        return jsonify(roles), 200
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
        task = task_manager.create_task(server_id, data)
        return jsonify(task), 201
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/tasks/<task_id>', methods=['PUT'])
@require_guild_access
def update_task(server_id, task_id):
    try:
        data = request.get_json()
        task_manager.update_task(server_id, task_id, data)
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/tasks/<task_id>', methods=['DELETE'])
@require_guild_access
def delete_task(server_id, task_id):
    try:
        task_manager.delete_task(server_id, task_id)
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
        shop_manager.delete_item(server_id, item_id)
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

# ========== TRANSACTIONS ==========
@app.route('/api/<server_id>/transactions', methods=['GET'])
@require_guild_access
def get_transactions(server_id):
    try:
        transactions = transaction_manager.get_transactions(server_id)
        return jsonify({'transactions': transactions}), 200
    except Exception as e:
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
        announcement = announcement_manager.create_announcement(server_id, data)
        return jsonify(announcement), 201
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
        embed = embed_builder.create_embed(server_id, data)
        return jsonify(embed), 201
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
        
        # Save config
        data_manager.save_guild_data(server_id, 'config', current_config)
        
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

# ========== STATIC FILES ==========
@app.route('/')
def serve_dashboard():
    return send_from_directory('web', 'index.html')

@app.route('/script.js')
def serve_script():
    return send_from_directory('web', 'script.js')

@app.route('/styles.css')
def serve_styles():
    return send_from_directory('web', 'styles.css')

@app.route('/favicon.ico')
def serve_favicon():
    return '', 204

# ========== ERROR HANDLERS ==========
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal error: {e}")
    return jsonify({'error': 'Internal server error'}), 500

# ========== STARTUP ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
