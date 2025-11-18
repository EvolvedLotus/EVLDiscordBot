from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context, g
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
import json
import os
import time as time_module
import queue
import asyncio
import threading
from datetime import datetime, timedelta, timezone
import subprocess
import logging
import logging.handlers
from collections import defaultdict
import hashlib
import secrets
import traceback
import sys
import functools

# System monitoring
import psutil

# Discord imports for message creation
import discord
from discord import Embed
from discord.ui import View, Button

# Load environment variables (only for local development)
if os.getenv('ENVIRONMENT') != 'production':
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed in production

# Environment variable validation for Railway deployment
REQUIRED_ENV_VARS = {
    'DISCORD_TOKEN': 'Discord bot token',
    'SUPABASE_URL': 'Supabase project URL',
    'SUPABASE_SERVICE_ROLE_KEY': 'Supabase service role key',
    'JWT_SECRET_KEY': 'JWT secret for authentication',
    'PORT': 'Server port (Railway auto-assigns)',
}

missing = []
for var, description in REQUIRED_ENV_VARS.items():
    if not os.getenv(var):
        missing.append(f"{var} ({description})")

if missing:
    print("❌ MISSING REQUIRED ENVIRONMENT VARIABLES:")
    for m in missing:
        print(f"  - {m}")
    sys.exit(1)

# Import data manager for server-specific data access
try:
    from core import data_manager as data_manager_module
    from core.transaction_manager import TransactionManager
except ImportError:
    data_manager_module = None
    TransactionManager = None

# Global data manager instance (set by set_data_manager)
data_manager_instance = None

# === LOGGING CONFIGURATION ===

def setup_logging():
    """Setup logging configuration for Railway deployment"""

    # Determine logs directory based on environment
    if os.environ.get('RAILWAY_ENVIRONMENT_ID') or os.environ.get('RAILWAY_PROJECT_ID'):
        # Railway: Use /tmp which is writable in ephemeral containers
        logs_dir = '/tmp/logs'
    else:
        # Local development: Use ./logs directory
        logs_dir = os.path.join(os.getcwd(), 'logs')

    # Create logs directory if it doesn't exist
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create logs directory: {e}")
        # Fallback to stdout only logging
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[logging.StreamHandler()]
        )
        return logging.getLogger(__name__)

    # Setup logging - Railway uses stdout only, local development uses both file and stdout
    is_railway = os.environ.get('RAILWAY_ENVIRONMENT_ID') or os.environ.get('RAILWAY_PROJECT_ID')

    if is_railway:
        # Railway: Only stdout (captured by Railway logs)
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[logging.StreamHandler()]
        )
    else:
        # Local development: Both file and stdout
        log_file = os.path.join(logs_dir, 'bot.log')
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

    return logging.getLogger(__name__)

# Initialize logging
logger = setup_logging()

# ============================================
# FLASK APP INITIALIZATION - MUST BE EARLY
# ============================================
app = Flask(__name__, static_folder='.')

# Configure JWT
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'your-jwt-secret-key-change-in-production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)

# Initialize JWTManager
jwt = JWTManager(app)

# Configure CORS for security - allow only specific frontend origins
# No wildcard origins in production
allowed_origins = []

# Add Railway public domain if available (for Railway-hosted frontend)
railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
if railway_domain:
    railway_url = f"https://{railway_domain}"
    allowed_origins.append(railway_url)

# Add Railway static URL if available (for Railway-hosted frontend)
railway_static_url = os.getenv('RAILWAY_STATIC_URL')
if railway_static_url:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(railway_static_url)
        railway_static_domain = f"{parsed.scheme}://{parsed.netloc}"
        if railway_static_domain not in allowed_origins:
            allowed_origins.append(railway_static_domain)
    except:
        pass

# Add Netlify domain if API_BASE_URL is set (extract domain)
api_base_url = os.getenv('API_BASE_URL')
if api_base_url:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(api_base_url)
        frontend_domain = f"{parsed.scheme}://{parsed.netloc}"
        if frontend_domain not in allowed_origins:
            allowed_origins.append(frontend_domain)
    except:
        pass

# Add Netlify domains from environment variables
netlify_site_url = os.getenv('NETLIFY_SITE_URL')
if netlify_site_url:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(netlify_site_url)
        netlify_domain = f"{parsed.scheme}://{parsed.netloc}"
        if netlify_domain not in allowed_origins:
            allowed_origins.append(netlify_domain)
    except:
        pass

# Add specific allowed frontend domains from environment variable
allowed_frontend_domains = os.getenv('ALLOWED_FRONTEND_DOMAINS', '')
if allowed_frontend_domains:
    domains = [d.strip() for d in allowed_frontend_domains.split(',') if d.strip()]
    for domain in domains:
        if domain not in allowed_origins:
            # Ensure domain has https:// prefix
            if not domain.startswith('http'):
                domain = f"https://{domain}"
            allowed_origins.append(domain)

# For Railway deployments, if no specific origins configured, allow Railway domains
is_railway = os.getenv('RAILWAY_ENVIRONMENT_ID') or os.getenv('RAILWAY_PROJECT_ID')
if is_railway and not allowed_origins:
    # Allow Railway domains by default for Railway deployments
    railway_project_id = os.getenv('RAILWAY_PROJECT_ID')
    if railway_project_id:
        # Allow common Railway domain patterns
        allowed_origins.extend([
            f"https://{railway_project_id}.up.railway.app",
            f"https://railway.app",
            "https://railway.app"
        ])
    # Also allow localhost for development on Railway
    allowed_origins.extend(['http://localhost:3000', 'http://localhost:5000'])

# For local development, allow localhost if no production domains configured
is_production = is_railway or os.getenv('PRODUCTION')
if not is_production and not allowed_origins:
    # Only allow localhost for development
    allowed_origins = ['http://localhost:3000', 'http://localhost:5000', 'http://127.0.0.1:3000', 'http://127.0.0.1:5000']

# If still no origins configured, log warning but allow Railway domains for Railway deployments
if not allowed_origins:
    if is_railway:
        logger.info("🚂 Railway deployment detected - allowing Railway domains for CORS")
        allowed_origins = ["https://railway.app", "https://*.up.railway.app"]
    else:
        logger.warning("⚠️  No CORS origins configured! Set ALLOWED_FRONTEND_DOMAINS environment variable")
        # Don't allow wildcard - require explicit configuration
        allowed_origins = []

CORS(app, resources={
    r"/api/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Admin-Token", "Cache-Control"],
        "supports_credentials": True,
        "expose_headers": ["Content-Type", "X-CSRFToken"]
    },
    r"/api/stream": {
        "origins": allowed_origins,
        "methods": ["GET"],
        "allow_headers": ["Cache-Control"],
        "supports_credentials": False,
        "expose_headers": []
    }
})

# Performance monitoring decorator
def performance_monitor(func):
    """Decorator to monitor function performance"""
    @functools.wraps(func)
    def performance_wrapper(*args, **kwargs):
        start_time = time_module.time()
        try:
            result = func(*args, **kwargs)
            duration = (time_module.time() - start_time) * 1000  # Convert to milliseconds
            logger.info(
                f"Function {func.__name__} completed successfully",
                extra={
                    'funcName': func.__name__,
                    'duration': f"{duration:.2f}",
                    'status': 'success'
                }
            )
            return result
        except Exception as e:
            duration = (time_module.time() - start_time) * 1000
            logger.error(
                f"Function {func.__name__} failed: {str(e)}",
                extra={
                    'funcName': func.__name__,
                    'duration': f"{duration:.2f}",
                    'status': 'error'
                },
                exc_info=True
            )
            raise
    return performance_wrapper

# Request logging middleware
@app.before_request
def log_request_info():
    """Log incoming requests"""
    g.start_time = time_module.time()
    g.request_id = f"req_{int(time_module.time() * 1000)}_{hash(request.remote_addr) % 10000}"

    # Skip logging for health checks and SSE
    if request.path in ['/api/health', '/api/stream']:
        return

    logger.info(
        f"Incoming {request.method} {request.path}",
        extra={
            'client_ip': request.remote_addr,
            'method': request.method,
            'path': request.path,
            'user_agent': request.headers.get('User-Agent', ''),
            'request_id': g.request_id
        }
    )

@app.after_request
def log_response_info(response):
    """Log response information"""
    duration = (time_module.time() - getattr(g, 'start_time', time_module.time())) * 1000

    # Skip logging for health checks and SSE
    if request.path in ['/api/health', '/api/stream']:
        return response

    logger.info(
        f"Response {response.status_code} for {request.method} {request.path}",
        extra={
            'client_ip': request.remote_addr,
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'duration': f"{duration:.2f}",
            'request_id': getattr(g, 'request_id', 'unknown')
        }
    )

    return response

# Import bot instance for user data access (lazy import to avoid startup issues)
bot = None
bot_thread = None
bot_ready = False

# ============= ROLE MANAGEMENT =============

@app.route('/api/<server_id>/roles', methods=['GET'])
@session_required
def get_guild_roles(server_id):
    """Get all roles for a guild with sync from Discord"""
    try:
        bot = get_bot()
        if not bot:
            return jsonify({'error': 'Bot not ready'}), 503

        guild = bot.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        # Sync roles from Discord to database
        roles_data = []
        for role in guild.roles:
            role_data = {
                'role_id': str(role.id),
                'role_name': role.name,
                'role_color': str(role.color),
                'role_position': role.position,
                'is_managed': role.managed,
                'permissions': role.permissions.value
            }
            roles_data.append(role_data)

            # Upsert to database
            data_manager.supabase.table('guild_roles').upsert({
                'guild_id': server_id,
                **role_data,
                'last_synced': datetime.now(timezone.utc).isoformat()
            }, on_conflict='guild_id,role_id').execute()

        return jsonify({
            'success': True,
            'roles': roles_data
        })
    except Exception as e:
        logger.error(f"Error fetching roles: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/<server_id>/users/<user_id>/roles', methods=['GET', 'PUT'])
@session_required
def manage_user_roles(server_id, user_id):
    """Get or update user roles"""
    try:
        bot = get_bot()
        if not bot:
            return jsonify({'error': 'Bot not ready'}), 503

        guild = bot.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        member = guild.get_member(int(user_id))
        if not member:
            return jsonify({'error': 'Member not found'}), 404

        if request.method == 'GET':
            # Return current roles
            roles = [{'id': str(r.id), 'name': r.name, 'color': str(r.color)}
                     for r in member.roles if r.name != "@everyone"]
            return jsonify({'success': True, 'roles': roles})

        elif request.method == 'PUT':
            # Update roles
            data = request.get_json()
            role_ids_to_add = data.get('add_roles', [])
            role_ids_to_remove = data.get('remove_roles', [])
            moderator_id = session.get('user', {}).get('user_id')

            # Add roles
            for role_id in role_ids_to_add:
                role = guild.get_role(int(role_id))
                if role and role not in member.roles:
                    asyncio.run_coroutine_threadsafe(
                        member.add_roles(role, reason=f"Modified by CMS admin"),
                        bot.loop
                    ).result(timeout=10)

                    # Log to database
                    data_manager.supabase.table('user_roles').upsert({
                        'guild_id': server_id,
                        'user_id': user_id,
                        'role_id': role_id,
                        'assigned_by': moderator_id
                    }, on_conflict='guild_id,user_id,role_id').execute()

            # Remove roles
            for role_id in role_ids_to_remove:
                role = guild.get_role(int(role_id))
                if role and role in member.roles:
                    asyncio.run_coroutine_threadsafe(
                        member.remove_roles(role, reason=f"Modified by CMS admin"),
                        bot.loop
                    ).result(timeout=10)

                    # Remove from database
                    data_manager.supabase.table('user_roles').delete().match({
                        'guild_id': server_id,
                        'user_id': user_id,
                        'role_id': role_id
                    }).execute()

            # Broadcast update
            broadcast_update('user.roles.updated', {
                'guild_id': server_id,
                'user_id': user_id,
                'added': role_ids_to_add,
                'removed': role_ids_to_remove
            })

            return jsonify({'success': True, 'message': 'Roles updated'})

    except Exception as e:
        logger.error(f"Error managing user roles: {e}")
        return jsonify({'error': str(e)}), 500


# ============= COMMAND PERMISSIONS =============

@app.route('/api/<server_id>/permissions/commands', methods=['GET'])
@session_required
def get_command_permissions(server_id):
    """Get all command permissions for guild"""
    try:
        result = data_manager.supabase.table('command_permissions').select('*').eq('guild_id', server_id).execute()
        return jsonify({'success': True, 'permissions': result.data})
    except Exception as e:
        logger.error(f"Error fetching command permissions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/<server_id>/permissions/commands/<command_name>', methods=['PUT'])
@session_required
def update_command_permissions(server_id, command_name):
    """Update permissions for specific command"""
    try:
        data = request.get_json()

        permission_data = {
            'guild_id': server_id,
            'command_name': command_name,
            'allowed_roles': data.get('allowed_roles', []),
            'denied_roles': data.get('denied_roles', []),
            'allowed_users': data.get('allowed_users', []),
            'denied_users': data.get('denied_users', []),
            'is_enabled': data.get('is_enabled', True),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        data_manager.supabase.table('command_permissions').upsert(
            permission_data,
            on_conflict='guild_id,command_name'
        ).execute()

        # Invalidate cache
        data_manager.invalidate_cache(server_id, 'command_permissions')

        broadcast_update('command.permissions.updated', {
            'guild_id': server_id,
            'command_name': command_name
        })

        return jsonify({'success': True, 'message': 'Permissions updated'})
    except Exception as e:
        logger.error(f"Error updating command permissions: {e}")
        return jsonify({'error': str(e)}), 500


# ============= MODERATION ACTIONS =============

@app.route('/api/<server_id>/moderation/kick', methods=['POST'])
@session_required
def kick_user(server_id):
    """Kick user from guild"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        reason = data.get('reason', 'No reason provided')
        moderator_id = session.get('user', {}).get('user_id')

        bot = get_bot()
        if not bot:
            return jsonify({'error': 'Bot not ready'}), 503

        guild = bot.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        member = guild.get_member(int(user_id))
        if not member:
            return jsonify({'error': 'Member not found'}), 404

        # Execute kick
        asyncio.run_coroutine_threadsafe(
            member.kick(reason=f"[CMS] {reason}"),
            bot.loop
        ).result(timeout=10)

        # Log action
        action_id = f"kick_{server_id}_{user_id}_{int(datetime.now().timestamp())}"
        data_manager.supabase.table('moderation_actions').insert({
            'action_id': action_id,
            'guild_id': server_id,
            'user_id': user_id,
            'action_type': 'kick',
            'reason': reason,
            'moderator_id': moderator_id
        }).execute()

        broadcast_update('moderation.kick', {
            'guild_id': server_id,
            'user_id': user_id,
            'moderator_id': moderator_id,
            'reason': reason
        })

        return jsonify({'success': True, 'message': 'User kicked'})
    except Exception as e:
        logger.error(f"Error kicking user: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/<server_id>/moderation/ban', methods=['POST'])
@session_required
def ban_user(server_id):
    """Ban user from guild"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        reason = data.get('reason', 'No reason provided')
        delete_message_days = data.get('delete_message_days', 0)
        moderator_id = session.get('user', {}).get('user_id')

        bot = get_bot()
        if not bot:
            return jsonify({'error': 'Bot not ready'}), 503

        guild = bot.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        # Execute ban
        async def _ban_user():
            user = await bot.fetch_user(int(user_id))
            await guild.ban(user, reason=f"[CMS] {reason}", delete_message_days=delete_message_days)

        asyncio.run_coroutine_threadsafe(_ban_user(), bot.loop).result(timeout=10)

        # Log action
        action_id = f"ban_{server_id}_{user_id}_{int(datetime.now().timestamp())}"
        data_manager.supabase.table('moderation_actions').insert({
            'action_id': action_id,
            'guild_id': server_id,
            'user_id': user_id,
            'action_type': 'ban',
            'reason': reason,
            'moderator_id': moderator_id
        }).execute()

        broadcast_update('moderation.ban', {
            'guild_id': server_id,
            'user_id': user_id,
            'moderator_id': moderator_id,
            'reason': reason
        })

        return jsonify({'success': True, 'message': 'User banned'})
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/<server_id>/moderation/timeout', methods=['POST'])
@session_required
def timeout_user(server_id):
    """Timeout user (mute) for specified duration"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        duration_minutes = data.get('duration_minutes', 60)
        reason = data.get('reason', 'No reason provided')
        moderator_id = session.get('user', {}).get('user_id')

        bot = get_bot()
        if not bot:
            return jsonify({'error': 'Bot not ready'}), 503

        guild = bot.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        member = guild.get_member(int(user_id))
        if not member:
            return jsonify({'error': 'Member not found'}), 404

        # Calculate timeout duration
        until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

        # Execute timeout
        asyncio.run_coroutine_threadsafe(
            member.timeout(until, reason=f"[CMS] {reason}"),
            bot.loop
        ).result(timeout=10)

        # Log action
        action_id = f"timeout_{server_id}_{user_id}_{int(datetime.now().timestamp())}"
        data_manager.supabase.table('moderation_actions').insert({
            'action_id': action_id,
            'guild_id': server_id,
            'user_id': user_id,
            'action_type': 'timeout',
            'reason': reason,
            'duration_seconds': duration_minutes * 60,
            'moderator_id': moderator_id,
            'expires_at': until.isoformat()
        }).execute()

        broadcast_update('moderation.timeout', {
            'guild_id': server_id,
            'user_id': user_id,
            'moderator_id': moderator_id,
            'duration_minutes': duration_minutes,
            'reason': reason
        })

        return jsonify({'success': True, 'message': f'User timed out for {duration_minutes} minutes'})
    except Exception as e:
        logger.error(f"Error timing out user: {e}")
        return jsonify({'error': str(e)}), 500


# ============= CHANNEL CONFIGURATION =============

@app.route('/api/<server_id>/channels', methods=['GET'])
@session_required
def get_guild_channels(server_id):
    """Get all text channels in guild - ALREADY EXISTS but ensure it works"""
    try:
        bot = get_bot()
        if not bot:
            return jsonify({'error': 'Bot not ready'}), 503

        guild = bot.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404

        channels = [
            {
                'id': str(channel.id),
                'name': channel.name,
                'position': channel.position,
                'category': channel.category.name if channel.category else None
            }
            for channel in guild.text_channels
        ]

        return jsonify({'success': True, 'channels': channels})
    except Exception as e:
        logger.error(f"Error fetching channels: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/<server_id>/config/channels', methods=['PUT'])
@session_required
def update_channel_config(server_id):
    """Update channel assignments (task, shop, welcome, logs)"""
    try:
        data = request.get_json()

        update_data = {}
        if 'task_channel_id' in data:
            update_data['task_channel_id'] = data['task_channel_id']
        if 'shop_channel_id' in data:
            update_data['shop_channel_id'] = data['shop_channel_id']
        if 'welcome_channel' in data:
            update_data['welcome_channel'] = data['welcome_channel']
        if 'logs_channel' in data:
            update_data['logs_channel'] = data['logs_channel']
        if 'log_channel' in data:  # Legacy support
            update_data['log_channel'] = data['log_channel']

        if not update_data:
            return jsonify({'error': 'No channels provided'}), 400

        update_data['last_channel_sync'] = datetime.now(timezone.utc).isoformat()
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()

        data_manager.supabase.table('guilds').update(update_data).eq('guild_id', server_id).execute()

        # Invalidate cache
        data_manager.invalidate_cache(server_id, 'config')

        broadcast_update('guild.channels.updated', {
            'guild_id': server_id,
            'channels': update_data
        })

        return jsonify({'success': True, 'message': 'Channel configuration updated', 'data': update_data})
    except Exception as e:
        logger.error(f"Error updating channel config: {e}")
        return jsonify({'error': str(e)}), 500


# ============= MONEY MANAGEMENT =============

@app.route('/api/<server_id>/users/<user_id>/balance/add', methods=['POST'])
@session_required
def add_user_balance(server_id, user_id):
    """Add money to user balance"""
    try:
        data = request.get_json()
        amount = data.get('amount')
        reason = data.get('reason', 'Added by admin')

        if not amount or amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400

        # Get current balance
        user_result = data_manager.supabase.table('users').select('balance').match({
            'guild_id': server_id,
            'user_id': user_id
        }).execute()

        if not user_result.data:
            return jsonify({'error': 'User not found'}), 404

        current_balance = user_result.data[0]['balance']
        new_balance = current_balance + amount

        # Update balance
        data_manager.supabase.table('users').update({
            'balance': new_balance,
            'total_earned': data_manager.supabase.rpc('increment', {'row_id': user_result.data[0]['id'], 'x': amount}),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).match({
            'guild_id': server_id,
            'user_id': user_id
        }).execute()

        # Log transaction
        transaction_id = f"admin_add_{server_id}_{user_id}_{int(datetime.now().timestamp())}"
        data_manager.supabase.table('transactions').insert({
            'transaction_id': transaction_id,
            'user_id': user_id,
            'guild_id': server_id,
            'amount': amount,
            'balance_before': current_balance,
            'balance_after': new_balance,
            'transaction_type': 'admin_add',
            'description': reason
        }).execute()

        broadcast_update('user.balance.updated', {
            'guild_id': server_id,
            'user_id': user_id,
            'balance': new_balance
        })

        return jsonify({'success': True, 'new_balance': new_balance})
    except Exception as e:
        logger.error(f"Error adding balance: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/<server_id>/users/<user_id>/balance/remove', methods=['POST'])
@session_required
def remove_user_balance(server_id, user_id):
    """Remove money from user balance"""
    try:
        data = request.get_json()
        amount = data.get('amount')
        reason = data.get('reason', 'Removed by admin')

        if not amount or amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400

        # Get current balance
        user_result = data_manager.supabase.table('users').select('balance').match({
            'guild_id': server_id,
            'user_id': user_id
        }).execute()

        if not user_result.data:
            return jsonify({'error': 'User not found'}), 404

        current_balance = user_result.data[0]['balance']

        if current_balance < amount:
            return jsonify({'error': 'Insufficient balance'}), 400

        new_balance = current_balance - amount

        # Update balance
        data_manager.supabase.table('users').update({
            'balance': new_balance,
            'total_spent': data_manager.supabase.rpc('increment', {'row_id': user_result.data[0]['id'], 'x': amount}),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).match({
            'guild_id': server_id,
            'user_id': user_id
        }).execute()

        # Log transaction
        transaction_id = f"admin_remove_{server_id}_{user_id}_{int(datetime.now().timestamp())}"
        data_manager.supabase.table('transactions').insert({
            'transaction_id': transaction_id,
            'user_id': user_id,
            'guild_id': server_id,
            'amount': -amount,
            'balance_before': current_balance,
            'balance_after': new_balance,
            'transaction_type': 'admin_remove',
            'description': reason
        }).execute()

        broadcast_update('user.balance.updated', {
            'guild_id': server_id,
            'user_id': user_id,
            'balance': new_balance
        })

        return jsonify({'success': True, 'new_balance': new_balance})
    except Exception as e:
        logger.error(f"Error removing balance: {e}")
        return jsonify({'error': str(e)}), 500

# Import bot instance for user data access (lazy import to avoid startup issues)
bot = None
bot_thread = None
bot_ready = False

def get_bot():
    """Get the bot instance"""
    global bot
    return bot

def run_bot():
    """Run bot in separate thread"""
    global bot, bot_ready
    try:
        import asyncio
        from bot import run_bot as bot_run_func
        asyncio.run(bot_run_func())
    except Exception as e:
        print(f"Error running bot: {e}")
        import traceback
        traceback.print_exc()

def start_bot_thread():
    """Start bot in separate thread before Flask starts"""
    global bot_thread, bot_ready
    import threading
    import time

    print("Starting Discord bot in separate thread...")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Wait for bot to be ready
    print("Waiting for bot to be ready...")
    timeout = 30  # 30 second timeout
    elapsed = 0
    while not bot_ready and elapsed < timeout:
        time_module.sleep(0.5)
        elapsed += 0.5
        if get_bot() and hasattr(get_bot(), 'is_ready') and get_bot().is_ready():
            bot_ready = True
            break

    if bot_ready:
        print("✅ Bot is ready!")
    else:
        print("⚠️  Bot startup timeout - continuing anyway")

def set_bot_ready():
    """Mark bot as ready"""
    global bot_ready
    bot_ready = True

# Configuration
DATA_DIR = os.getenv('DATA_DIR', 'data')
LOGS_FILE = os.path.join(DATA_DIR, 'logs.json')
STATUS_FILE = os.path.join(DATA_DIR, 'status.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
COMMANDS_FILE = os.path.join(DATA_DIR, 'commands.json')
TASKS_FILE = os.path.join(DATA_DIR, 'tasks.json')

# Simple session-based authentication
SESSIONS = {}  # session_id -> user_data
SESSION_TIMEOUT = 3600  # 1 hour in seconds

# Session-based authentication middleware decorator
def session_required(f):
    """Decorator to require session-based authentication"""
    @functools.wraps(f)
    def session_wrapper(*args, **kwargs):
        session_id = request.cookies.get('session_id')
        if not session_id:
            return jsonify({'error': 'Authentication required'}), 401

        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'Session expired or invalid'}), 401

        # Add user to request context
        request.user = session['user']
        return f(*args, **kwargs)
    return session_wrapper

def create_session(user_data: dict):
    """Create a new session and return session ID"""
    session_id = secrets.token_hex(32)
    SESSIONS[session_id] = {
        'user': user_data,
        'created_at': time_module.time(),
        'expires_at': time_module.time() + SESSION_TIMEOUT
    }
    return session_id

def get_session(session_id: str):
    """Get session data if valid"""
    if session_id not in SESSIONS:
        return None

    session = SESSIONS[session_id]
    if time_module.time() > session['expires_at']:
        # Session expired, remove it
        del SESSIONS[session_id]
        return None

    return session

def destroy_session(session_id: str):
    """Destroy a session"""
    SESSIONS.pop(session_id, None)

def authenticate_user(username: str, password: str):
    """Authenticate user with username/password"""
    # Simple authentication - in production, use proper user management
    # For now, check against environment variables or simple config
    admin_username = os.getenv('ADMIN_USERNAME', 'admin')
    admin_password = os.getenv('ADMIN_PASSWORD', 'admin')

    # Hash password for comparison (simple hash, use proper hashing in production)
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    stored_hash = hashlib.sha256(admin_password.encode()).hexdigest()

    if username == admin_username and hashed_password == stored_hash:
        return {"username": username, "role": "admin"}
    return None

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Bypass authentication for SSE endpoint
@app.before_request
def bypass_auth_for_sse():
    """Bypass authentication checks for SSE endpoint"""
    if request.path == '/api/stream':
        # Skip all authentication middleware for SSE
        return None

# Initialize data files if they don't exist
def init_data_files():
    files_to_init = [LOGS_FILE, STATUS_FILE, SETTINGS_FILE, COMMANDS_FILE, TASKS_FILE]
    for file_path in files_to_init:
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                if 'logs' in file_path:
                    json.dump([], f)
                elif 'status' in file_path:
                    json.dump({
                        'botOnline': False,
                        'uptime': 0,
                        'servers': 0,
                        'users': 0,
                        'commandsUsed': 0,
                        'lastUpdate': datetime.now().isoformat()
                    }, f)
                elif 'settings' in file_path:
                    json.dump({
                        'auto-restart': True,
                        'debug-mode': False,
                        'profanity-filter': True,
                        'link-filter': True,
                        'currency-system': True,
                        'item-shop': True,
                        'chatbot': False
                    }, f)
                elif 'commands' in file_path or 'tasks' in file_path:
                    json.dump([], f)

init_data_files()

# Helper functions
def read_json_file(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def write_json_file(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

def log_event(level, message):
    logs = read_json_file(LOGS_FILE)
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'level': level,
        'message': message
    }
    logs.append(log_entry)
    # Keep only last 1000 logs
    if len(logs) > 1000:
        logs = logs[-1000:]
    write_json_file(LOGS_FILE, logs)

# Async helper functions for Discord message creation
async def _create_task_message(guild, task_id, task_data, config):
    """Helper to create Discord message for task"""
    task_channel_id = config.get("task_channel_id")

    if not task_channel_id:
        return None

    task_channel = guild.get_channel(int(task_channel_id))
    if not task_channel:
        return None

    # Create embed
    embed = Embed(
        title=f"📋 {task_data['name']}",
        description=task_data.get('description', 'No description'),
        color=discord.Color.blue()
    )
    embed.add_field(name="Reward", value=f"💰 {task_data['reward']} coins", inline=True)
    embed.add_field(name="Time Limit", value=f"⏰ {task_data['duration_hours']} hours", inline=True)
    embed.set_footer(text=f"Task ID: {task_id} | Use /claim {task_id} to start")

    try:
        message = await task_channel.send(embed=embed)
        return message.id
    except discord.Forbidden:
        print(f"No permission to send message in {task_channel.name}")
        return None

async def _create_shop_message(guild, item_id, item_data, config):
    """Helper to create Discord message for shop item"""
    shop_channel_id = config.get("shop_channel_id")

    if not shop_channel_id:
        return None

    shop_channel = guild.get_channel(int(shop_channel_id))
    if not shop_channel:
        return None

    # Create embed
    currency_symbol = config.get("currency_symbol", "$")
    embed = Embed(
        title=item_data['name'],
        description=item_data.get('description', 'No description'),
        color=discord.Color.green()
    )
    embed.add_field(name="Price", value=f"{currency_symbol}{item_data['price']}", inline=True)

    stock = item_data.get('stock', -1)
    stock_text = "♾️ Unlimited" if stock == -1 else f"📦 {stock} available"
    embed.add_field(name="Stock", value=stock_text, inline=True)

    category = item_data.get('category', 'misc')
    embed.add_field(name="Category", value=f"🏷️ {category.title()}", inline=True)

    embed.set_footer(text="Use /buy <item_id> to purchase")

    try:
        message = await shop_channel.send(embed=embed)
        return message.id
    except discord.Forbidden:
        print(f"No permission to send message in {shop_channel.name}")
        return None

async def _update_shop_message(guild, item_data, config):
    """Helper to update Discord shop item message"""
    shop_channel_id = config.get("shop_channel_id")
    message_id = item_data.get("message_id")

    if not shop_channel_id or not message_id:
        return

    shop_channel = guild.get_channel(int(shop_channel_id))
    if not shop_channel:
        return

    try:
        message = await shop_channel.fetch_message(int(message_id))

        # Create updated embed
        currency_symbol = config.get("currency_symbol", "$")
        embed = Embed(
            title=item_data['name'],
            description=item_data.get('description', 'No description'),
            color=discord.Color.green() if item_data.get('is_active', True) else discord.Color.grey()
        )
        embed.add_field(name="Price", value=f"{currency_symbol}{item_data['price']}", inline=True)

        stock = item_data.get('stock', -1)
        stock_text = "♾️ Unlimited" if stock == -1 else f"📦 {stock} available"
        embed.add_field(name="Stock", value=stock_text, inline=True)

        category = item_data.get('category', 'misc')
        embed.add_field(name="Category", value=f"🏷️ {category.title()}", inline=True)

        embed.set_footer(text="Use /buy <item_id> to purchase")

        # Update message
        await message.edit(embed=embed)
    except discord.NotFound:
        print(f"Shop message {message_id} not found, may need recreation")
    except discord.Forbidden:
        print(f"No permission to edit message in shop channel")

async def create_task_message_and_update(guild, server_id, task_id, task, post_announcement):
    """
    Create Discord task message with embed and optionally post announcement.
    Returns dict with message IDs.
    """
    result = {}

    try:
        # Get task channel
        channel = guild.get_channel(int(task['channel_id']))
        if not channel:
            raise ValueError(f"Channel {task['channel_id']} not found")

        # Create embed
        embed = create_task_embed(task)

        # Add claim button view
        view = TaskClaimView(task_id)

        # Send message
        message = await channel.send(embed=embed, view=view)
        result['task_message'] = str(message.id)

        # Post announcement if requested
        if post_announcement:
            config = data_manager_instance.load_guild_data(server_id, 'config')
            announcement_channel_id = (
                config.get('features', {}).get('task_announcement_channel') or
                task['channel_id']
            )

            announcement_channel = guild.get_channel(int(announcement_channel_id))
            if announcement_channel:
                announcement_embed = discord.Embed(
                    title="🆕 New Task Available!",
                    description=f"**{task['name']}** has been posted!",
                    color=discord.Color.green()
                )
                announcement_embed.add_field(
                    name="Reward",
                    value=f"{task['reward']} coins",
                    inline=True
                )
                announcement_embed.add_field(
                    name="Duration",
                    value=f"{task['duration_hours']} hours",
                    inline=True
                )
                announcement_embed.add_field(
                    name="View Task",
                    value=f"[Jump to Task]({message.jump_url})",
                    inline=False
                )

                announcement = await announcement_channel.send(embed=announcement_embed)
                result['announcement'] = str(announcement.id)

        return result

    except Exception as e:
        app.logger.error(f"Discord message creation error: {e}", exc_info=True)
        raise

def create_task_embed(task):
    """Create consistent task embed for Discord messages."""
    from datetime import datetime
    embed = discord.Embed(
        title=f"📋 {task['name']}",
        description=task['description'],
        color=discord.Color.blue(),
        timestamp=datetime.fromisoformat(task['created'])
    )

    if task.get('url'):
        embed.add_field(name="🔗 Link", value=task['url'], inline=False)

    embed.add_field(name="💰 Reward", value=f"{task['reward']} coins", inline=True)
    embed.add_field(name="⏱️ Duration", value=f"{task['duration_hours']} hours", inline=True)

    if task.get('role_name'):
        embed.add_field(name="🎭 Role Reward", value=task['role_name'], inline=True)

    # Status indicator
    status_emoji = {
        'active': '🟢',
        'pending': '🟡',
        'completed': '✅',
        'expired': '⏰',
        'cancelled': '❌'
    }
    embed.add_field(
        name="Status",
        value=f"{status_emoji.get(task['status'], '⚪')} {task['status'].title()}",
        inline=True
    )

    # Claims info
    max_claims_text = "Unlimited" if task['max_claims'] == -1 else task['max_claims']
    embed.add_field(
        name="👥 Claims",
        value=f"{task['current_claims']}/{max_claims_text}",
        inline=True
    )

    # Expiry countdown
    expires_at = datetime.fromisoformat(task['expires_at'])
    embed.add_field(
        name="⏰ Expires",
        value=f"<t:{int(expires_at.timestamp())}:R>",
        inline=True
    )

    embed.set_footer(text=f"Task ID: {task['id']}")

    return embed

# === AUTHENTICATION ===

@app.route('/api/auth/login', methods=['POST'], endpoint='login')
def login():
    """Authenticate user and create session"""
    try:
        # Validate request data
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400

        if len(username) > 50 or len(password) > 100:
            return jsonify({'error': 'Username or password too long'}), 400

        # Authenticate user
        user = authenticate_user(username, password)
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401

        # Create session
        session_id = create_session(user)

        # Set session cookie
        response = jsonify({
            'message': 'Login successful',
            'user': {
                'username': user['username'],
                'role': user['role']
            }
        })

        # Set session cookie
        response.set_cookie(
            'session_id',
            session_id,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite='Lax',
            max_age=SESSION_TIMEOUT
        )

        return response

    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON format'}), 400
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({'error': 'Authentication failed'}), 500

@app.route('/api/auth/me', methods=['GET'], endpoint='get_current_user_info')
def get_current_user_info():
    """Get current authenticated user info"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'error': 'Not authenticated'}), 401

    session = get_session(session_id)
    if not session:
        return jsonify({'error': 'Session expired'}), 401

    user = session['user']
    return jsonify({
        'username': user['username'],
        'role': user.get('role', 'user')
    })

@app.route('/api/auth/logout', methods=['POST'], endpoint='logout')
def logout():
    """Logout user by destroying session"""
    session_id = request.cookies.get('session_id')
    if session_id:
        destroy_session(session_id)

    response = jsonify({'message': 'Logged out successfully'})
    response.set_cookie('session_id', '', expires=0, httponly=True, secure=False, samesite='Lax')
    return response

@app.route('/api/auth/validate', methods=['GET'], endpoint='validate_session')
def validate_session():
    """Validates current session"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({'valid': False, 'error': 'No session'}), 401

    session = get_session(session_id)
    if not session:
        return jsonify({'valid': False, 'error': 'Session expired'}), 401

    user = session['user']
    return jsonify({'valid': True, 'user': {'username': user['username'], 'role': user.get('role', 'user')}}), 200

# Routes
@app.route('/api/health', endpoint='health_check')
def health_check():
    """Comprehensive health check endpoint for Railway deployment monitoring"""
    try:
        # For Railway deployment, return healthy immediately during startup
        # Railway sets RAILWAY_PROJECT_ID, RAILWAY_ENVIRONMENT_ID, etc.
        railway_env = bool(os.getenv('RAILWAY_PROJECT_ID') or os.getenv('RAILWAY_ENVIRONMENT_ID'))
        if railway_env:
            # Simple health check for Railway - just confirm Flask is running
            return jsonify({
                "status": "healthy",
                "timestamp": time_module.time(),
                "version": "2.0",
                "environment": {
                    "railway_env": True,
                    "message": "Railway deployment - basic health check passed"
                }
            }), 200

        # Check if bot is running
        bot_status = check_bot_running()

        # Check database connectivity and get detailed status
        db_status = "unknown"
        db_details = {}
        if data_manager_instance:
            try:
                # Get connection status from DataManager
                connection_status = data_manager_instance.get_connection_status()
                db_status = "healthy" if connection_status.get('healthy') else "degraded"
                db_details = {
                    "connection_healthy": connection_status.get('healthy'),
                    "degraded_mode": connection_status.get('degraded_mode'),
                    "consecutive_failures": connection_status.get('consecutive_failures'),
                    "cache_size": connection_status.get('cache_size'),
                    "uptime_seconds": connection_status.get('uptime_seconds')
                }

                # Try a simple database operation
                guilds = data_manager_instance.get_all_guilds()
                db_details["guilds_count"] = len(guilds) if guilds else 0

            except Exception as e:
                db_status = f"error: {str(e)}"
                db_details["error"] = str(e)

        # Check system resources
        system_info = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_mb": psutil.virtual_memory().used / 1024 / 1024,
            "memory_total_mb": psutil.virtual_memory().total / 1024 / 1024,
            "disk_percent": psutil.disk_usage('/').percent,
            "uptime_seconds": time_module.time() - psutil.boot_time()
        }

        # Check application performance
        performance_info = {}
        if data_manager_instance and hasattr(data_manager_instance, 'get_performance_stats'):
            try:
                perf_stats = data_manager_instance.get_performance_stats()
                performance_info = {
                    "db_loads": perf_stats.get('loads', 0),
                    "db_saves": perf_stats.get('saves', 0),
                    "cache_hit_rate": perf_stats.get('cache_hit_rate', 0),
                    "db_connection_errors": perf_stats.get('db_connection_errors', 0),
                    "db_retry_attempts": perf_stats.get('db_retry_attempts', 0),
                    "operations_per_second": perf_stats.get('operations_per_second', 0)
                }
            except Exception as e:
                performance_info["error"] = str(e)

        # Determine overall health status
        services_healthy = {
            "bot": bot_status,
            "database": db_status == "healthy",
            "web_server": True,
            "system_resources": (
                system_info["cpu_percent"] < 90 and
                system_info["memory_percent"] < 90 and
                system_info["disk_percent"] < 95
            )
        }

        overall_status = "healthy"
        if not all(services_healthy.values()):
            overall_status = "degraded"
        if not services_healthy["bot"] and not services_healthy["database"]:
            overall_status = "unhealthy"

        health_data = {
            "status": overall_status,
            "timestamp": time_module.time(),
            "version": "2.0",
            "services": {
                "bot": "healthy" if services_healthy["bot"] else "unhealthy",
                "database": db_status,
                "web_server": "healthy",
                "system_resources": "healthy" if services_healthy["system_resources"] else "warning"
            },
            "database": db_details,
            "system": system_info,
            "performance": performance_info,
            "environment": {
                "python_version": f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}",
                "flask_env": os.getenv('FLASK_ENV', 'production'),
                "railway_env": bool(os.getenv('RAILWAY_ENVIRONMENT')),
                "netlify_env": bool(os.getenv('NETLIFY'))
            }
        }

        # Return appropriate HTTP status
        status_code = 200 if overall_status == "healthy" else (503 if overall_status == "unhealthy" else 200)
        return jsonify(health_data), status_code

    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": time_module.time(),
            "emergency_contact": "Check application logs for details"
        }), 500

@app.route('/', endpoint='serve_frontend')
def serve_frontend():
    return send_from_directory('.', 'index.html')

@app.route('/styles.css', endpoint='serve_css')
def serve_css():
    return send_from_directory('.', 'styles.css')

@app.route('/script.js', endpoint='serve_js')
def serve_js():
    return send_from_directory('.', 'script.js')

@app.route('/favicon.ico', endpoint='favicon')
def favicon():
    """Serve favicon or return 204 No Content"""
    # Option 1: Return empty response
    return '', 204

    # Option 2: Serve actual favicon if you have one
    # from flask import send_from_directory
    # return send_from_directory('static', 'favicon.ico')

@app.route('/api/servers', endpoint='get_servers')
def get_servers():
    """Get list of all servers the bot is in"""
    servers = []

    # First try to get from bot instance
    bot_instance = get_bot()
    if bot_instance and hasattr(bot_instance, 'guilds') and len(bot_instance.guilds) > 0:
        for guild in bot_instance.guilds:
            # Get server-specific data
            config = {}
            currency_data = {}
            if data_manager_instance:
                try:
                    config = data_manager_instance.load_guild_data(guild.id, "config")
                    currency_data = data_manager_instance.load_guild_data(guild.id, "currency")
                except Exception as e:
                    logging.error(f"Error loading data for guild {guild.id}: {e}")

            servers.append({
                'id': str(guild.id),
                'name': guild.name,
                'member_count': guild.member_count,
                'icon_url': str(guild.icon.url) if guild.icon else None,
                'owner_id': str(guild.owner_id),
                'created_at': guild.created_at.isoformat(),
                'prefix': config.get('prefix', '!'),
                'currency_symbol': config.get('currency_symbol', '$'),
                'currency_name': config.get('currency_name', 'coins'),
                'total_users': len(currency_data.get('users', {})),
                'total_currency': currency_data.get('metadata', {}).get('total_currency', 0)
            })
    else:
        # Fallback: get servers from data manager if bot is not available
        if data_manager_instance:
            try:
                guild_ids = data_manager_instance.get_all_guilds()
                for guild_id in guild_ids:
                    config = {}
                    currency_data = {}
                    try:
                        config = data_manager_instance.load_guild_data(guild_id, "config")
                        currency_data = data_manager_instance.load_guild_data(guild_id, "currency")
                    except Exception as e:
                        logging.error(f"Error loading data for guild {guild_id}: {e}")

                    # Try to get cached server info from config
                    server_name = config.get('server_name', f'Server {guild_id}')
                    member_count = config.get('member_count', 0)

                    servers.append({
                        'id': str(guild_id),
                        'name': server_name,
                        'member_count': member_count,
                        'icon_url': config.get('icon_url'),
                        'owner_id': config.get('owner_id', '0'),
                        'created_at': config.get('created_at', datetime.now().isoformat()),
                        'prefix': config.get('prefix', '!'),
                        'currency_symbol': config.get('currency_symbol', '$'),
                        'currency_name': config.get('currency_name', 'coins'),
                        'total_users': len(currency_data.get('users', {})),
                        'total_currency': currency_data.get('metadata', {}).get('total_currency', 0)
                    })
            except Exception as e:
                logging.error(f"Error getting guilds from data manager: {e}")

    return jsonify({'servers': servers})

@app.route('/api/status', endpoint='get_status')
def get_status():
    status = read_json_file(STATUS_FILE)
    # Check if bot is actually running
    bot_running = check_bot_running()
    status['botOnline'] = bot_running
    if bot_running:
        # Update uptime if bot is running
        status['uptime'] = calculate_uptime()
    write_json_file(STATUS_FILE, status)
    return jsonify(status)

@app.route('/api/logs', endpoint='get_logs')
def get_logs():
    level_filter = request.args.get('level', 'all')
    logs = read_json_file(LOGS_FILE)

    if level_filter != 'all':
        logs = [log for log in logs if log['level'] == level_filter]

    return jsonify(logs[-100:])  # Return last 100 logs

@app.route('/api/logs', methods=['DELETE'], endpoint='clear_logs')
def clear_logs():
    write_json_file(LOGS_FILE, [])
    log_event('info', 'Logs cleared by admin')
    return jsonify({'message': 'Logs cleared'})

@app.route('/api/commands', endpoint='get_commands')
def get_commands():
    commands = read_json_file(COMMANDS_FILE)
    return jsonify(commands)

@app.route('/api/commands', methods=['POST'], endpoint='add_command')
def add_command():
    data = request.get_json()
    name = data.get('name', '').strip()
    response = data.get('response', '').strip()

    if not name or not response:
        return jsonify({'error': 'Name and response are required'}), 400

    commands = read_json_file(COMMANDS_FILE)

    # Check if command already exists
    if any(cmd['name'] == name for cmd in commands):
        return jsonify({'error': 'Command already exists'}), 400

    commands.append({
        'name': name,
        'response': response,
        'created': datetime.now().isoformat()
    })

    write_json_file(COMMANDS_FILE, commands)
    log_event('info', f'Custom command added: {name}')
    return jsonify({'message': 'Command added'})

@app.route('/api/commands/<name>', methods=['DELETE'], endpoint='delete_command')
def delete_command(name):
    commands = read_json_file(COMMANDS_FILE)
    commands = [cmd for cmd in commands if cmd['name'] != name]
    write_json_file(COMMANDS_FILE, commands)
    log_event('info', f'Custom command deleted: {name}')
    return jsonify({'message': 'Command deleted'})

# === SHOP ITEMS ===

@app.route('/api/<server_id>/shop', methods=['GET'], endpoint='get_shop_items')
def get_shop_items(server_id):
    """
    Query parameters:
    - category (optional)
    - active_only (default: true)
    - include_out_of_stock (default: false)

    Returns all shop items with filtering
    """
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)  # No transaction manager needed for read operations

        guild_id = int(server_id)
        category = request.args.get('category')
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        include_out_of_stock = request.args.get('include_out_of_stock', 'false').lower() == 'true'

        items = shop_manager.get_shop_items(
            guild_id,
            category=category,
            active_only=active_only,
            include_out_of_stock=include_out_of_stock
        )

        return jsonify({'items': items})

    except Exception as e:
        logging.error(f"Error getting shop items for server {server_id}: {e}")
        return jsonify({'error': 'Failed to load shop items'}), 500

@app.route('/api/<server_id>/shop/<item_id>', methods=['GET'], endpoint='get_shop_item')
def get_shop_item(server_id, item_id):
    """Get single item details"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)

        item = shop_manager.get_item(int(server_id), item_id)
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        return jsonify({'item': item})

    except Exception as e:
        logging.error(f"Error getting shop item {item_id} for server {server_id}: {e}")
        return jsonify({'error': 'Failed to load shop item'}), 500

@app.route('/api/<server_id>/shop', methods=['POST'], endpoint='create_shop_item')
@jwt_required
def create_shop_item(server_id):
    """Create new shop item and post to Discord"""
    try:
        data = request.json

        # Validate required fields
        required_fields = ['name', 'description', 'price', 'category']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Validate price is positive integer
        try:
            price = int(data['price'])
            if price < 0:
                return jsonify({'error': 'Price must be positive'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid price format'}), 400

        # Load config to get shop_channel_id
        config = data_manager_instance.load_guild_data(server_id, 'config')
        shop_channel_id = config.get('shop_channel_id')

        if not shop_channel_id:
            return jsonify({'error': 'Shop channel not configured. Set it in Server Config first.'}), 400

        # Validate guild and channel asynchronously
        async def _validate_guild_and_channel():
            guild = bot.get_guild(int(server_id))
            if not guild:
                return None, 'Server not found'

            channel = guild.get_channel(int(shop_channel_id))
            if not channel:
                return None, f'Shop channel {shop_channel_id} not found'

            return guild, channel

        try:
            future = asyncio.run_coroutine_threadsafe(
                _validate_guild_and_channel(),
                bot.loop
            )
            guild, channel = future.result(timeout=10)
            if not guild:
                return jsonify({'error': channel}), 404  # channel contains error message
        except Exception as e:
            return jsonify({'error': f'Failed to validate server/channel: {str(e)}'}), 500

        # Generate unique item ID
        item_id = f"item_{int(time_module.time() * 1000)}"

        # Prepare item data
        item_data = {
            'name': data['name'],
            'description': data['description'],
            'price': price,
            'category': data.get('category', 'general'),
            'stock': data.get('stock', -1),  # -1 = unlimited
            'is_active': data.get('is_active', True),
            'emoji': data.get('emoji', '🛒'),
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        # Create Discord embed for shop item
        embed = discord.Embed(
            title=f"{item_data['emoji']} {item_data['name']}",
            description=item_data['description'],
            color=discord.Color.blue()
        )
        embed.add_field(name="Price", value=f"{price} coins", inline=True)

        stock_display = "Unlimited" if item_data['stock'] == -1 else str(item_data['stock'])
        embed.add_field(name="Stock", value=stock_display, inline=True)
        embed.add_field(name="Category", value=item_data['category'], inline=True)
        embed.set_footer(text="Use /buy <item_id> to purchase")

        # Send message to Discord
        try:
            message = run_discord_task(channel.send(embed=embed))
            item_data['message_id'] = str(message.id)
            item_data['channel_id'] = str(shop_channel_id)
        except discord.Forbidden:
            return jsonify({'error': 'Bot lacks permission to post in shop channel'}), 403
        except Exception as e:
            logger.error(f"Failed to post shop message: {e}")
            return jsonify({'error': f'Failed to post to Discord: {str(e)}'}), 500

        # Save to database
        currency_data = data_manager_instance.load_guild_data(server_id, 'currency')
        if 'shop_items' not in currency_data:
            currency_data['shop_items'] = {}

        currency_data['shop_items'][item_id] = item_data
        data_manager_instance.save_guild_data(server_id, 'currency', currency_data)

        # Broadcast SSE event
        sse_manager.broadcast_event('shop_item_created', {
            'guild_id': server_id,
            'item_id': item_id,
            'item': item_data
        })

        logger.info(f"Shop item created: {item_id} in guild {server_id}")

        return jsonify({
            'success': True,
            'item_id': item_id,
            'item': item_data
        }), 201

    except Exception as e:
        logger.error(f"Error creating shop item: {e}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/<server_id>/shop/<item_id>', methods=['PUT'], endpoint='update_shop_item')
def update_shop_item(server_id, item_id):
    """
    Update shop item.
    Body: {name, price, description, stock, category, emoji, is_active, role_requirement}
    (all fields optional)
    """
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        # Admin authorization check
        guild_id = int(server_id)
        config = data_manager_instance.load_guild_data(guild_id, "config")
        admin_roles = config.get('admin_roles', [])
        dashboard_tokens = config.get('dashboard_tokens', [])

        # Check admin token authentication
        admin_token = request.headers.get('X-Admin-Token') or request.args.get('admin_token')
        has_valid_token = False
        if admin_token and dashboard_tokens:
            has_valid_token = admin_token in dashboard_tokens

        if not has_valid_token:
            return jsonify({'error': 'Admin authorization required'}), 403

        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)

        data = request.get_json()

        item = shop_manager.update_item(guild_id, item_id, data)

        # Update Discord message
        bot_instance = get_bot()
        if bot_instance:
            future = asyncio.run_coroutine_threadsafe(
                shop_manager.sync_discord_message(guild_id, item_id, bot_instance),
                bot_instance.loop
            )
            future.result(timeout=5)

        log_event('info', f'Shop item updated in server {server_id}: {item_id}')
        return jsonify({'success': True, 'item': item})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logging.error(f"Error updating shop item in server {server_id}: {e}")
        return jsonify({'error': 'Failed to update shop item'}), 500

@app.route('/api/<server_id>/shop/<item_id>', methods=['DELETE'], endpoint='delete_shop_item')
@jwt_required
def delete_shop_item(server_id, item_id):
    """Delete shop item and remove Discord message"""
    try:
        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)  # No transaction manager needed for delete

        success = shop_manager.delete_item(int(server_id), item_id)
        if not success:
            return jsonify({'error': 'Item not found'}), 404

        logger.info(f"Shop item deleted: {item_id} from guild {server_id}")
        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error deleting shop item: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# === STOCK MANAGEMENT ===

@app.route('/api/<server_id>/shop/<item_id>/stock', methods=['GET'], endpoint='get_item_stock')
def check_stock(server_id, item_id):
    """Get current stock status"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)

        stock_info = shop_manager.check_stock(int(server_id), item_id)
        return jsonify(stock_info)

    except Exception as e:
        logging.error(f"Error checking stock for item {item_id} in server {server_id}: {e}")
        return jsonify({'error': 'Failed to check stock'}), 500

@app.route('/api/<server_id>/shop/<item_id>/stock', methods=['PUT'], endpoint='update_item_stock')
def update_stock(server_id, item_id):
    """
    Update item stock.
    Body: {
        quantity: int,
        operation: 'set' | 'add' | 'subtract'
    }
    """
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)

        data = request.get_json()
        quantity = data.get('quantity')
        operation = data.get('operation', 'set')

        if quantity is None:
            return jsonify({'error': 'Quantity required'}), 400

        stock_info = shop_manager.update_stock(
            int(server_id),
            item_id,
            quantity,
            operation
        )

        # Update Discord message
        bot_instance = get_bot()
        if bot_instance:
            future = asyncio.run_coroutine_threadsafe(
                shop_manager.sync_discord_message(int(server_id), item_id, bot_instance),
                bot_instance.loop
            )
            future.result(timeout=5)

        log_event('info', f'Stock updated for item {item_id} in server {server_id}: {operation} {quantity}')
        return jsonify({'success': True, 'stock': stock_info})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logging.error(f"Error updating stock for item {item_id} in server {server_id}: {e}")
        return jsonify({'error': 'Failed to update stock'}), 500

# === INVENTORY ===

@app.route('/api/<server_id>/inventory/<user_id>', methods=['GET'], endpoint='get_user_inventory')
def get_user_inventory(server_id, user_id):
    """Get user inventory with item details"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)

        include_details = request.args.get('include_details', 'true').lower() == 'true'

        inventory = shop_manager.get_inventory(
            int(server_id),
            int(user_id),
            include_item_details=include_details
        )

        return jsonify({'inventory': inventory})

    except Exception as e:
        logging.error(f"Error getting inventory for user {user_id} in server {server_id}: {e}")
        return jsonify({'error': 'Failed to load inventory'}), 500

@app.route('/api/<server_id>/inventory/<user_id>/export', methods=['GET'], endpoint='export_user_inventory')
def export_user_inventory(server_id, user_id):
    """Export inventory as CSV/JSON"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)

        format_type = request.args.get('format', 'json')

        if format_type == 'csv':
            csv_data = shop_manager.export_inventory(int(server_id), int(user_id), 'csv')
            return Response(
                csv_data,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment;filename=inventory_{user_id}.csv'}
            )
        else:
            json_data = shop_manager.export_inventory(int(server_id), int(user_id), 'json')
            return Response(
                json_data,
                mimetype='application/json',
                headers={'Content-Disposition': f'attachment;filename=inventory_{user_id}.json'}
            )

    except Exception as e:
        logging.error(f"Error exporting inventory for user {user_id} in server {server_id}: {e}")
        return jsonify({'error': 'Failed to export inventory'}), 500

@app.route('/api/<server_id>/inventory/export', methods=['GET'], endpoint='export_all_inventories')
def export_all_inventories(server_id):
    """Export all user inventories (admin only)"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)

        format_type = request.args.get('format', 'json')

        data = shop_manager.export_inventory(int(server_id), None, format_type)

        if format_type == 'csv':
            return Response(
                data,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment;filename=all_inventories.csv'}
            )
        else:
            return Response(
                data,
                mimetype='application/json',
                headers={'Content-Disposition': f'attachment;filename=all_inventories.json'}
            )

    except Exception as e:
        logging.error(f"Error exporting all inventories for server {server_id}: {e}")
        return jsonify({'error': 'Failed to export inventories'}), 500

# === STATISTICS ===

@app.route('/api/<server_id>/shop/statistics', methods=['GET'], endpoint='get_shop_statistics')
def get_shop_statistics(server_id):
    """
    Get shop statistics.
    Query params: period (day/week/month/all, default: all)
    """
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        from core.shop_manager import ShopManager
        from core.transaction_manager import TransactionManager

        # Create TransactionManager instance for shop statistics
        tm = TransactionManager(data_manager_instance)
        shop_manager = ShopManager(data_manager_instance, tm)

        period = request.args.get('period', 'all')

        stats = shop_manager.get_shop_statistics(int(server_id), period)

        return jsonify({'statistics': stats})

    except Exception as e:
        logging.error(f"Error getting shop statistics for server {server_id}: {e}")
        return jsonify({'error': 'Failed to load statistics'}), 500

# === VALIDATION ===

@app.route('/api/<server_id>/shop/validate', methods=['POST'], endpoint='validate_shop_integrity')
def validate_shop_integrity(server_id):
    """Validate shop data integrity"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        from core.shop_manager import ShopManager
        shop_manager = ShopManager(data_manager_instance, None)

        validation = shop_manager.validate_shop_integrity(int(server_id))

        return jsonify(validation)

    except Exception as e:
        logging.error(f"Error validating shop integrity for server {server_id}: {e}")
        return jsonify({'error': 'Failed to validate shop'}), 500

@app.route('/api/<server_id>/users/<user_id>', methods=['GET'], endpoint='get_user_details')
def get_user_details(server_id, user_id):
    """Get detailed information for a specific user"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)
        user_id_int = int(user_id)

        # Get bot instance for Discord user info
        bot_instance = get_bot()
        if not bot_instance:
            return jsonify({'error': 'Bot not available'}), 503

        guild = bot_instance.get_guild(guild_id)
        if not guild:
            return jsonify({'error': 'Server not found'}), 404

        member = guild.get_member(user_id_int)
        if not member:
            return jsonify({'error': 'User not found in server'}), 404

        # Load currency data
        currency_data = data_manager_instance.load_guild_data(guild_id, "currency")
        user_data = currency_data.get('users', {}).get(str(user_id), {})

        # Load inventory
        inventory = currency_data.get('inventory', {}).get(str(user_id), {})

        # Load transaction history (recent 10)
        transactions_data = data_manager_instance.load_guild_data(guild_id, "transactions") or []
        if isinstance(transactions_data, list):
            user_transactions = [
                txn for txn in transactions_data
                if str(txn.get('user_id', '')) == str(user_id)
            ]
            # Sort by timestamp descending and take last 10
            user_transactions.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            user_transactions = user_transactions[:10]
        else:
            user_transactions = []

        # Build response
        user_details = {
            'user_id': str(user_id),
            'username': member.name,
            'display_name': member.display_name,
            'discriminator': member.discriminator,
            'avatar_url': str(member.avatar.url) if member.avatar else None,
            'joined_at': member.joined_at.isoformat() if member.joined_at else None,
            'roles': [role.name for role in member.roles if role.name != '@everyone'],
            'balance': user_data.get('balance', 0),
            'total_earned': user_data.get('total_earned', 0),
            'total_spent': user_data.get('total_spent', 0),
            'last_daily': user_data.get('last_daily'),
            'inventory': inventory,
            'is_active': user_data.get('is_active', True),
            'recent_transactions': user_transactions
        }

        return jsonify(user_details)

    except ValueError as e:
        return jsonify({'error': 'Invalid user ID format'}), 400
    except Exception as e:
        logger.error(f"Error getting user details for {user_id} in server {server_id}: {e}")
        return jsonify({'error': 'Failed to load user details'}), 500

# ===== EMBEDS =====





# ===== ANNOUNCEMENTS =====

@app.route('/api/<server_id>/announcements', methods=['POST'], endpoint='create_announcement')
@jwt_required
def create_announcement(server_id):
    """Create and post announcement"""
    try:
        announcement_data = request.json

        admin_cog = bot_instance.get_cog('Admin')
        if not admin_cog:
            return jsonify({'error': 'Admin cog not loaded'}), 500

        future = asyncio.run_coroutine_threadsafe(
            admin_cog.post_announcement(
                int(server_id),
                announcement_data['channel_id'],
                announcement_data['content'],
                announcement_data.get('embed'),
                announcement_data.get('mention_role')
            ),
            bot_instance.loop
        )

        result = future.result(timeout=10)

        sse_manager.broadcast_event('announcement_posted', {
            'guild_id': server_id,
            'result': result
        })

        return jsonify(result), 201
    except Exception as e:
        logger.error(f"Error creating announcement: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/users', endpoint='get_users')
def get_users(server_id):
    """Get users for a specific server with pagination support"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        # Parse pagination parameters
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 200)  # Max 200 per page
        sort_by = request.args.get('sort_by', 'balance')
        sort_dir = request.args.get('sort_dir', 'desc')
        include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

        bot_instance = get_bot()
        currency_data = data_manager_instance.load_guild_data(int(server_id), "currency")

        users_list = []
        if bot_instance and hasattr(bot_instance, 'guilds'):
            guild = bot_instance.get_guild(int(server_id))
            if guild:
                for member in guild.members:
                    if not member.bot:
                        user_id = str(member.id)
                        user_data = currency_data.get('users', {}).get(user_id, {})
                        inventory = currency_data.get('inventory', {}).get(user_id, {})

                        # Skip inactive users unless requested
                        if not include_inactive and not user_data.get('is_active', True):
                            continue

                        users_list.append({
                            'id': user_id,
                            'username': member.name,
                            'discriminator': member.discriminator,
                            'display_name': member.display_name,
                            'avatar_url': str(member.avatar.url) if member.avatar else None,
                            'balance': user_data.get('balance', 0),
                            'total_earned': user_data.get('total_earned', 0),
                            'total_spent': user_data.get('total_spent', 0),
                            'inventory': inventory,
                            'joined_at': member.joined_at.isoformat() if member.joined_at else None,
                            'roles': [role.name for role in member.roles if role.name != '@everyone'],
                            'is_active': user_data.get('is_active', True)
                        })

        # Sort users
        valid_sort_fields = ['balance', 'total_earned', 'total_spent', 'username', 'joined_at']
        if sort_by not in valid_sort_fields:
            sort_by = 'balance'

        reverse = sort_dir == 'desc'
        if sort_by == 'joined_at':
            # Handle datetime sorting
            users_list.sort(key=lambda x: x[sort_by] or '', reverse=reverse)
        else:
            users_list.sort(key=lambda x: x[sort_by], reverse=reverse)

        # Calculate totals before pagination
        total_balance = sum(user.get('balance', 0) for user in users_list)
        total_users = len(users_list)

        # Paginate
        start = (page - 1) * per_page
        end = start + per_page
        paginated_users = users_list[start:end]

        return jsonify({
            'users': paginated_users,
            'total_users': total_users,
            'total_balance': total_balance,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_users + per_page - 1) // per_page,
            'has_more': end < total_users
        })
    except Exception as e:
        logging.error(f"Error getting users for server {server_id}: {e}")
        return jsonify({
            'users': [],
            'total_users': 0,
            'total_balance': 0,
            'page': 1,
            'per_page': 50,
            'total_pages': 0,
            'has_more': False
        })

# Rate limiting for balance modifications
balance_modification_limits = defaultdict(lambda: {'count': 0, 'reset_time': time_module.time() + 60})

def check_balance_modification_rate_limit(server_id, user_id):
    """Check rate limit for balance modifications (max 5 per minute per server)"""
    key = f"{server_id}_{user_id}"
    current_time = time_module.time()

    # Reset counter if time window passed
    if current_time > balance_modification_limits[key]['reset_time']:
        balance_modification_limits[key] = {'count': 0, 'reset_time': current_time + 60}

    # Check limit
    if balance_modification_limits[key]['count'] >= 5:
        return False, int(balance_modification_limits[key]['reset_time'] - current_time)

    # Increment counter
    balance_modification_limits[key]['count'] += 1
    return True, 0

@app.route('/api/<server_id>/users/<user_id>/balance', methods=['PUT'], endpoint='modify_user_balance')
def modify_user_balance(server_id, user_id):
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        # Check rate limit
        allowed, retry_after = check_balance_modification_rate_limit(server_id, user_id)
        if not allowed:
            return jsonify({
                'error': f'Rate limit exceeded. Try again in {retry_after} seconds.',
                'retry_after': retry_after
            }), 429

        # Get request data
        data = request.json
        amount = int(data.get('amount', 0))
        set_balance = data.get('set', False)
        reason = data.get('reason', 'Admin modification via CMS')
        admin_token = data.get('admin_token', '')

        # Validate reason is provided and not empty
        if not reason or not reason.strip():
            return jsonify({'error': 'Reason is required for balance modifications'}), 400

        # Validate reason length (prevent abuse)
        if len(reason.strip()) > 500:
            return jsonify({'error': 'Reason must be 500 characters or less'}), 400

        guild_id = int(server_id)

        # Load server config to check admin roles and tokens
        config = data_manager_instance.load_guild_data(guild_id, "config")
        admin_roles = config.get('admin_roles', [])
        dashboard_tokens = config.get('dashboard_tokens', [])

        # Check admin token authentication (for web dashboard)
        has_valid_token = False
        if admin_token and dashboard_tokens:
            has_valid_token = admin_token in dashboard_tokens

        # If no valid token, check if admin token is configured for this server
        if not has_valid_token:
            # For backward compatibility, check if server has dashboard access enabled
            dashboard_enabled = config.get('dashboard_enabled', False)
            if not dashboard_enabled:
                return jsonify({'error': 'Dashboard access not enabled for this server'}), 403

            # If dashboard is enabled but no token provided, assume authenticated admin
            # (This is for development - in production, proper authentication should be implemented)
            has_valid_token = True

        if not has_valid_token:
            return jsonify({'error': 'Invalid or missing admin token'}), 403

        # Get bot instance to validate server exists
        bot_instance = get_bot()
        if not bot_instance:
            return jsonify({'error': 'Bot not available'}), 503

        guild = bot_instance.get_guild(guild_id)
        if not guild:
            return jsonify({'error': 'Server not found'}), 404

        currency_data = data_manager_instance.load_guild_data(guild_id, "currency")

        if not currency_data:
            return jsonify({'error': 'Currency data not found'}), 404

        user_id_str = str(user_id)

        # Initialize user if doesn't exist
        if user_id_str not in currency_data.get('users', {}):
            currency_data.setdefault('users', {})[user_id_str] = {
                'balance': 0,
                'total_earned': 0,
                'total_spent': 0,
                'created_at': datetime.now().isoformat()
            }

        user_data = currency_data['users'][user_id_str]
        balance_before = user_data['balance']

        # Calculate new balance
        if set_balance:
            balance_after = amount
            actual_change = amount - balance_before
        else:
            balance_after = balance_before + amount
            actual_change = amount

        # Update balance
        user_data['balance'] = balance_after

        # Update totals
        if actual_change > 0:
            user_data['total_earned'] = user_data.get('total_earned', 0) + actual_change
        elif actual_change < 0:
            user_data['total_spent'] = user_data.get('total_spent', 0) + abs(actual_change)

        # Create transaction log with validation
        transactions = data_manager_instance.load_guild_data(guild_id, "transactions") or []
        if not isinstance(transactions, list):
            transactions = []

        # Validate transaction data
        transaction_data = {
            'id': f"txn_{int(time_module.time() * 1000)}",
            'user_id': user_id_str,
            'amount': actual_change,
            'balance_before': balance_before,
            'balance_after': balance_after,
            'type': 'admin_adjustment',
            'description': reason,
            'timestamp': datetime.now().isoformat(),
            'source': 'cms'
        }

        # Validate required fields
        required_fields = ['id', 'user_id', 'amount', 'balance_before', 'balance_after', 'type', 'description', 'timestamp']
        for field in required_fields:
            if field not in transaction_data or transaction_data[field] is None:
                return jsonify({'error': f'Missing required transaction field: {field}'}), 500

        # Validate data types and ranges
        if not isinstance(transaction_data['amount'], (int, float)):
            return jsonify({'error': 'Transaction amount must be a number'}), 500
        if not isinstance(transaction_data['balance_before'], (int, float)):
            return jsonify({'error': 'Balance before must be a number'}), 500
        if not isinstance(transaction_data['balance_after'], (int, float)):
            return jsonify({'error': 'Balance after must be a number'}), 500

        # Validate amount consistency (balance_after should equal balance_before + amount)
        expected_balance = transaction_data['balance_before'] + transaction_data['amount']
        if abs(expected_balance - transaction_data['balance_after']) > 0.01:  # Allow small floating point differences
            return jsonify({'error': 'Transaction balance calculation inconsistency'}), 500

        # Validate user_id format
        if not isinstance(transaction_data['user_id'], str) or not transaction_data['user_id'].strip():
            return jsonify({'error': 'Invalid user ID format'}), 500

        # Validate transaction type
        valid_types = ['admin_adjustment', 'daily_reward', 'task_reward', 'shop_purchase', 'transfer']
        if transaction_data['type'] not in valid_types:
            return jsonify({'error': f'Invalid transaction type: {transaction_data["type"]}'}), 500

        # Validate description
        if not isinstance(transaction_data['description'], str) or not transaction_data['description'].strip():
            return jsonify({'error': 'Transaction description is required'}), 500
        if len(transaction_data['description']) > 1000:
            return jsonify({'error': 'Transaction description too long (max 1000 characters)'}), 500

        # Validate timestamp format
        try:
            datetime.fromisoformat(transaction_data['timestamp'])
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid timestamp format'}), 500

        transactions.append(transaction_data)

        # Save both files atomically
        data_manager_instance.save_guild_data(guild_id, "currency", currency_data)
        data_manager_instance.save_guild_data(guild_id, "transactions", transactions)

        # Invalidate cache and notify listeners
        data_manager_instance.invalidate_cache(guild_id, "currency")
        data_manager_instance.invalidate_cache(guild_id, "transactions")

        # Broadcast SSE event for real-time updates
        sse_manager.broadcast_event('balance_update', {
            'guild_id': str(guild_id),
            'user_id': user_id_str,
            'balance_before': balance_before,
            'balance_after': balance_after,
            'change': actual_change,
            'reason': reason,
            'source': 'cms'
        })

        return jsonify({
            'success': True,
            'balance_before': balance_before,
            'balance_after': balance_after,
            'change': actual_change
        })

    except Exception as e:
        logger.error(f"Error modifying balance: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/status', methods=['PUT'], endpoint='update_bot_status')
@jwt_required
def update_bot_status():
    """Update bot's Discord status and presence"""
    try:
        data = request.json

        status_type = data.get('status_type', 'playing')
        status_message = data.get('status_message', '')
        presence = data.get('presence', 'online')
        streaming_url = data.get('streaming_url')

        # Validate status type
        valid_types = ['playing', 'watching', 'listening', 'competing', 'streaming']
        if status_type not in valid_types:
            return jsonify({'error': 'Invalid status type'}), 400

        # Validate presence
        valid_presences = ['online', 'idle', 'dnd', 'invisible']
        if presence not in valid_presences:
            return jsonify({'error': 'Invalid presence'}), 400

        # Validate streaming URL if type is streaming
        if status_type == 'streaming' and not streaming_url:
            return jsonify({'error': 'Streaming URL required for streaming status'}), 400

        # Validate message length
        if len(status_message) > 128:
            return jsonify({'error': 'Status message too long (max 128 characters)'}), 400

        # Map to Discord enums
        activity_type_map = {
            'playing': discord.ActivityType.playing,
            'watching': discord.ActivityType.watching,
            'listening': discord.ActivityType.listening,
            'competing': discord.ActivityType.competing,
            'streaming': discord.ActivityType.streaming
        }

        status_map = {
            'online': discord.Status.online,
            'idle': discord.Status.idle,
            'dnd': discord.Status.dnd,
            'invisible': discord.Status.invisible
        }

        # Create activity
        if status_type == 'streaming':
            activity = discord.Streaming(
                name=status_message,
                url=streaming_url
            )
        else:
            activity = discord.Activity(
                type=activity_type_map[status_type],
                name=status_message
            )

        # Update bot status using asyncio.run_coroutine_threadsafe
        async def _update_presence():
            try:
                bot_instance = get_bot()
                if not bot_instance:
                    return False
                await bot_instance.change_presence(
                    activity=activity,
                    status=status_map[presence]
                )
                return True
            except Exception as e:
                logger.error(f"Failed to update bot status: {e}")
                return False

        # Run the async operation
        bot_instance = get_bot()
        if not bot_instance:
            return jsonify({'error': 'Bot not available'}), 500
        future = asyncio.run_coroutine_threadsafe(_update_presence(), bot_instance.loop)
        success = future.result(timeout=10)

        if not success:
            return jsonify({'error': 'Failed to update Discord status'}), 500

        # Save to global config for persistence
        try:
            import os
            config_dir = os.path.join('data', 'global')
            os.makedirs(config_dir, exist_ok=True)
            config_file = os.path.join(config_dir, 'config.json')

            # Load existing config
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    global_config = json.load(f)
            else:
                global_config = {}

            # Update bot status
            global_config['bot_status'] = {
                'type': status_type,
                'message': status_message,
                'presence': presence,
                'streaming_url': streaming_url if status_type == 'streaming' else None,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Save config
            with open(config_file, 'w') as f:
                json.dump(global_config, f, indent=2)

            logger.info("Bot status saved to global config file")

        except Exception as e:
            logger.error(f"Failed to save bot status to global config: {e}")

        logger.info(f"Bot status updated: {status_type} {status_message} ({presence})")

        return jsonify({
            'success': True,
            'status': global_config['bot_status']
        }), 200

    except Exception as e:
        logger.error(f"Error updating bot status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/status', methods=['GET'], endpoint='get_bot_status')
@jwt_required
def get_bot_status():
    """Get current bot status configuration"""
    try:
        global_config = data_manager_instance.load_global_data('config') or {}
        status = global_config.get('bot_status', {
            'type': 'playing',
            'message': f'{len(bot.guilds) if bot else 0} servers',
            'presence': 'online',
            'streaming_url': None
        })

        return jsonify(status), 200
    except Exception as e:
        logger.error(f"Error getting bot status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/status', methods=['PUT'], endpoint='update_server_bot_status')
def update_server_bot_status(server_id):
    """Update bot status for a specific server"""
    data = request.get_json()
    status_type = data.get('status', 'online')

    # Validate status type
    valid_statuses = ['online', 'idle', 'dnd', 'invisible']
    if status_type not in valid_statuses:
        return jsonify({'error': 'Invalid status type'}), 400

    try:
        # Get bot instance
        bot_instance = get_bot()
        if not bot_instance:
            return jsonify({'error': 'Bot not available'}), 503

        guild = bot_instance.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Server not found'}), 404

        # Update bot presence for this server
        # Note: Discord.py presence is global, not per-server
        # We'll update the global presence but log it per-server
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"Server: {guild.name}"
        )

        # Set status
        status_map = {
            'online': discord.Status.online,
            'idle': discord.Status.idle,
            'dnd': discord.Status.do_not_disturb,
            'invisible': discord.Status.invisible
        }

        # Update presence asynchronously
        async def update_presence():
            try:
                await bot_instance.change_presence(
                    status=status_map[status_type],
                    activity=activity
                )
                return True
            except Exception as e:
                logger.error(f"Failed to update bot presence: {e}")
                return False

        # Run async task
        future = asyncio.run_coroutine_threadsafe(
            update_presence(),
            bot_instance.loop
        )

        success = future.result(timeout=10)

        if not success:
            return jsonify({'error': 'Failed to update bot presence'}), 500

        # Log the status change
        log_event('info', f'Bot status updated to {status_type} for server {server_id} ({guild.name})')

        return jsonify({
            'message': f'Bot status updated to {status_type} for server {guild.name}',
            'status': status_type,
            'server_name': guild.name
        })

    except Exception as e:
        logger.error(f"Error updating server bot status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', endpoint='get_settings')
def get_settings():
    settings = read_json_file(SETTINGS_FILE)
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'], endpoint='update_settings')
def update_settings():
    data = request.get_json()
    write_json_file(SETTINGS_FILE, data)
    log_event('info', 'Settings updated by admin')
    return jsonify({'message': 'Settings updated'})

@app.route('/api/restart', methods=['POST'], endpoint='restart_bot')
def restart_bot():
    try:
        # Check if we're in the EVL server (1123738140050464878)
        # This is a safety check to only allow restart from authorized server
        server_id = request.args.get('server_id')
        if server_id != '1123738140050464878':
            return jsonify({'error': 'Restart not authorized for this server'}), 403

        # Kill existing bot process
        kill_bot_process()

        # Start new bot process in background
        import os
        import sys

        # Get the current working directory and Python executable
        cwd = os.getcwd()
        python_exe = sys.executable

        # Start bot in background
        process = subprocess.Popen(
            [python_exe, 'bot.py'],
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
        )

        log_event('info', f'Bot restart initiated by admin from server {server_id}')
        return jsonify({'message': 'Bot restart initiated successfully'})
    except Exception as e:
        log_event('error', f'Failed to restart bot: {str(e)}')
        return jsonify({'error': f'Failed to restart bot: {str(e)}'}), 500

@app.route('/api/<server_id>/config', endpoint='get_server_config')
def get_server_config(server_id):
    """Get configuration for a specific server"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        config = data_manager_instance.load_guild_data(int(server_id), "config")
        return jsonify(config)
    except Exception as e:
        logging.error(f"Error getting config for server {server_id}: {e}")
        return jsonify({'error': 'Failed to load server config'}), 500

@app.route('/api/<server_id>/config', methods=['PUT'], endpoint='update_server_config')
def update_server_config(server_id):
    """Update configuration for a specific server"""
    data = request.get_json()

    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        config = data_manager_instance.load_guild_data(int(server_id), "config")

        # Update allowed config fields
        allowed_fields = ['prefix', 'currency_name', 'currency_symbol', 'admin_roles', 'moderator_roles',
                         'log_channel', 'welcome_channel', 'features', 'global_shop', 'global_tasks']

        for key, value in data.items():
            if key in allowed_fields:
                config[key] = value

        data_manager_instance.save_guild_data(int(server_id), "config", config)

        # Force cache invalidation to ensure immediate runtime updates
        data_manager_instance.invalidate_cache(int(server_id), "config")

        log_event('info', f'Server {server_id} config updated')
        return jsonify({'message': 'Server config updated'})
    except Exception as e:
        logging.error(f"Error updating config for server {server_id}: {e}")
        return jsonify({'error': 'Failed to update server config'}), 500

@app.route('/api/<server_id>/tasks', endpoint='get_server_tasks')
def get_server_tasks(server_id):
    """Get tasks for a specific server"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        tasks_data = data_manager_instance.load_guild_data(int(server_id), "tasks")
        tasks_dict = tasks_data.get('tasks', {})
        # Convert dict to array for frontend compatibility
        tasks_array = list(tasks_dict.values())
        return jsonify(tasks_array)
    except Exception as e:
        logging.error(f"Error getting tasks for server {server_id}: {e}")
        return jsonify([])

def atomic_task_operation(server_id, operation_func):
    """
    Perform atomic task operations with rollback capability.
    Handles both tasks.json and potentially currency.json updates.
    Implements full rollback on failure by restoring temporary snapshots.
    """
    import os
    import tempfile
    import shutil

    # Load current data and create backups for rollback
    tasks_data = data_manager_instance.load_guild_data(server_id, 'tasks')
    currency_data = data_manager_instance.load_guild_data(server_id, 'currency')

    # Create temporary backup snapshots
    backup_dir = os.path.join('data', 'guilds', str(server_id), 'temp_backup')
    os.makedirs(backup_dir, exist_ok=True)

    tasks_backup_path = os.path.join(backup_dir, 'tasks_backup.json')
    currency_backup_path = os.path.join(backup_dir, 'currency_backup.json')

    try:
        # Create backup snapshots
        with open(tasks_backup_path, 'w') as f:
            json.dump(tasks_data, f, indent=2)

        with open(currency_backup_path, 'w') as f:
            json.dump(currency_data, f, indent=2)

        # Execute the operation
        result = operation_func(tasks_data, currency_data)

        # Save atomically
        updates = {'tasks': tasks_data}
        if result.get('currency_updated', False):
            updates['currency'] = currency_data

        success = data_manager_instance.atomic_transaction(server_id, updates)

        if not success:
            raise Exception("Failed to save atomic transaction")

        # Clean up backup files on success
        if os.path.exists(tasks_backup_path):
            os.remove(tasks_backup_path)
        if os.path.exists(currency_backup_path):
            os.remove(currency_backup_path)
        if os.path.exists(backup_dir) and not os.listdir(backup_dir):
            os.rmdir(backup_dir)

        return result

    except Exception as e:
        app.logger.error(f"Atomic task operation failed: {e}", exc_info=True)

        # Implement rollback by restoring backup snapshots
        try:
            app.logger.info(f"Rolling back atomic operation for server {server_id}")

            # Restore tasks data
            if os.path.exists(tasks_backup_path):
                with open(tasks_backup_path, 'r') as f:
                    restored_tasks_data = json.load(f)
                data_manager_instance.save_guild_data(server_id, 'tasks', restored_tasks_data)
                app.logger.info("Tasks data rolled back successfully")

            # Restore currency data if it was involved
            if os.path.exists(currency_backup_path):
                with open(currency_backup_path, 'r') as f:
                    restored_currency_data = json.load(f)
                data_manager_instance.save_guild_data(server_id, 'currency', restored_currency_data)
                app.logger.info("Currency data rolled back successfully")

        except Exception as rollback_error:
            app.logger.critical(f"CRITICAL: Rollback failed for server {server_id}: {rollback_error}", exc_info=True)
            # If rollback fails, we need to log this as a critical error
            log_event('critical', f'Atomic operation rollback failed for server {server_id}: {rollback_error}')

        # Clean up backup files
        try:
            if os.path.exists(tasks_backup_path):
                os.remove(tasks_backup_path)
            if os.path.exists(currency_backup_path):
                os.remove(currency_backup_path)
            if os.path.exists(backup_dir) and not os.listdir(backup_dir):
                os.rmdir(backup_dir)
        except Exception as cleanup_error:
            app.logger.warning(f"Failed to clean up backup files: {cleanup_error}")

        raise

@app.route('/api/<server_id>/tasks', methods=['POST'], endpoint='create_server_task')
@jwt_required
async def create_server_task(server_id):
    """Create new task and post to configured task channel"""
    try:
        # Validate request data
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400

        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Validate required fields
        required = ['name', 'description', 'reward', 'duration_hours']
        for field in required:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Validate data types and ranges
        try:
            reward = int(data['reward'])
            duration_hours = int(data['duration_hours'])
            if reward < 0 or duration_hours < 1:
                raise ValueError("Invalid reward or duration values")
            if len(data['name'].strip()) == 0:
                raise ValueError("Task name cannot be empty")
            if len(data['description'].strip()) == 0:
                raise ValueError("Task description cannot be empty")
            if len(data['name']) > 200:
                raise ValueError("Task name too long (max 200 characters)")
            if len(data['description']) > 2000:
                raise ValueError("Task description too long (max 2000 characters)")
        except (ValueError, TypeError) as e:
            return jsonify({'error': f'Validation error: {str(e)}'}), 400

        # Validate server_id format
        try:
            server_id_int = int(server_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid server ID format'}), 400

        # Validate guild access asynchronously
        async def _validate_guild():
            guild = bot.get_guild(server_id_int)
            if not guild:
                return None, 'Server not found'
            return guild, None

        try:
            future = asyncio.run_coroutine_threadsafe(_validate_guild(), bot.loop)
            guild, error = future.result(timeout=10)
            if error:
                return jsonify({'error': error}), 404
        except asyncio.TimeoutError:
            return jsonify({'error': 'Server validation timeout'}), 500
        except Exception as e:
            return jsonify({'error': f'Failed to validate server: {str(e)}'}), 500

        # AUTO-RESOLVE: Get task channel from Server Config
        try:
            config = data_manager_instance.load_guild_data(server_id, 'config')
            if not config:
                return jsonify({'error': 'Server configuration not found'}), 500
        except Exception as e:
            logger.error(f"Error loading server config: {e}")
            return jsonify({'error': 'Failed to load server configuration'}), 500

        task_channel_id = config.get('task_channel_id')
        if not task_channel_id:
            return jsonify({
                'error': 'Task channel not configured. Please set it in Server Config first.'
            }), 400

        # Validate channel exists and is accessible
        try:
            channel = guild.get_channel(int(task_channel_id))
            if not channel:
                return jsonify({
                    'error': f'Configured task channel (ID: {task_channel_id}) not found. Update Server Config.'
                }), 404
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid task channel ID format'}), 400

        # Load existing tasks data
        try:
            tasks_data = data_manager_instance.load_guild_data(server_id, 'tasks')
            if not tasks_data:
                tasks_data = {'tasks': {}, 'user_tasks': {}, 'metadata': {'next_task_id': 1}}
        except Exception as e:
            logger.error(f"Error loading tasks data: {e}")
            return jsonify({'error': 'Failed to load tasks data'}), 500

        # Generate task ID
        task_id = str(tasks_data.get('metadata', {}).get('next_task_id', 1))

        # Calculate expiry
        created = datetime.now(timezone.utc)
        expires_at = created + timedelta(hours=duration_hours)

        # Prepare task data
        task_data = {
            'id': int(task_id),
            'name': data['name'].strip(),
            'description': data['description'].strip(),
            'reward': reward,
            'duration_hours': duration_hours,
            'status': 'active',
            'created': created.isoformat(),
            'expires_at': expires_at.isoformat(),
            'channel_id': str(task_channel_id),
            'max_claims': data.get('max_claims', -1),
            'current_claims': 0,
            'assigned_users': [],
            'category': data.get('category', 'General'),
            'role_name': data.get('role_name', None)
        }

        # Post to Discord using tasks cog
        try:
            # Get tasks cog instance
            tasks_cog = bot.get_cog('Tasks')
            if not tasks_cog:
                return jsonify({'error': 'Tasks cog not available'}), 500

            # Post task message using cog method (async -> sync bridge)
            future = asyncio.run_coroutine_threadsafe(
                tasks_cog.post_task_to_discord(server_id, task_data),
                bot.loop
            )
            message_id = future.result(timeout=10)
            if not message_id:
                return jsonify({'error': 'Failed to post task to Discord'}), 500

            task_data['message_id'] = message_id
            logger.info(f"Task message posted: {message_id}")
        except asyncio.TimeoutError:
            logger.error("Discord post timed out")
            return jsonify({'error': 'Discord sync timeout'}), 500
        except Exception as e:
            logger.error(f"Failed to post task message: {e}")
            return jsonify({'error': f'Failed to post to Discord: {str(e)}'}), 500

        # Save to database
        try:
            if 'tasks' not in tasks_data:
                tasks_data['tasks'] = {}
            tasks_data['tasks'][task_id] = task_data

            # Update metadata
            if 'metadata' not in tasks_data:
                tasks_data['metadata'] = {}
            tasks_data['metadata']['next_task_id'] = int(task_id) + 1

            data_manager_instance.save_guild_data(server_id, 'tasks', tasks_data)
        except Exception as e:
            logger.error(f"Error saving task data: {e}")
            return jsonify({'error': 'Failed to save task data'}), 500

        # Broadcast SSE
        try:
            sse_manager.broadcast_event('task_created', {
                'guild_id': server_id,
                'task_id': task_id,
                'task': task_data
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast SSE event: {e}")

        logger.info(f"Task created: {task_id} in guild {server_id}")

        return jsonify({
            'success': True,
            'task_id': task_id,
            'task': task_data
        }), 201

    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON format'}), 400
    except Exception as e:
        logger.error(f"Error creating task: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/<server_id>/tasks/<task_id>', methods=['PUT'], endpoint='update_server_task')
def update_server_task(server_id, task_id):
    """
    Update task with Discord message sync.
    Only allows updating specific fields to prevent data corruption.
    """
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        data = request.json
        tasks_data = data_manager_instance.load_guild_data(int(server_id), 'tasks')
        task = tasks_data.get('tasks', {}).get(task_id)

        if not task:
            return jsonify({'error': 'Task not found'}), 404

        # Fields that can be updated
        updatable_fields = [
            'name', 'description', 'url', 'reward',
            'duration_hours', 'status', 'max_claims',
            'role_name', 'category'
        ]

        # Track what changed
        changes = {}
        for field in updatable_fields:
            if field in data and data[field] != task.get(field):
                changes[field] = {'old': task.get(field), 'new': data[field]}
                task[field] = data[field]

        # Recalculate expiry if duration changed
        if 'duration_hours' in changes:
            created = datetime.fromisoformat(task['created'])
            task['expires_at'] = (created + timedelta(hours=task['duration_hours'])).isoformat()

        # Prevent invalid status transitions
        valid_transitions = {
            'pending': ['active', 'cancelled'],
            'active': ['completed', 'cancelled', 'expired'],
            'completed': [],
            'expired': [],
            'cancelled': ['active']
        }

        if 'status' in changes:
            old_status = changes['status']['old']
            new_status = changes['status']['new']
            if new_status not in valid_transitions.get(old_status, []):
                return jsonify({
                    'error': f'Invalid status transition: {old_status} -> {new_status}'
                }), 400

        # Save changes
        data_manager_instance.save_guild_data(int(server_id), 'tasks', tasks_data)

        # Update Discord message
        guild = bot_instance.get_guild(int(server_id))
        if guild and task.get('message_id'):
            try:
                future = asyncio.run_coroutine_threadsafe(
                    update_task_message(guild, int(server_id), int(task_id), task),
                    bot_instance.loop
                )
                future.result(timeout=10)
            except Exception as e:
                app.logger.error(f"Error updating task message: {e}")

        return jsonify({
            'success': True,
            'task': task,
            'changes': changes
        })

    except Exception as e:
        app.logger.error(f"Task update error: {e}", exc_info=True)
        return jsonify({'error': 'Failed to update task'}), 500

async def update_task_message(guild, server_id, task_id, task):
    """Update Discord task message with current data."""
    if not task.get('message_id'):
        return

    try:
        channel = guild.get_channel(int(task['channel_id']))
        if not channel:
            app.logger.warning(f"Channel {task['channel_id']} not found")
            return

        message = await channel.fetch_message(int(task['message_id']))
        embed = create_task_embed(task)

        # Disable button if task is not active
        view = None
        if task['status'] == 'active':
            view = TaskClaimView(task_id)

        await message.edit(embed=embed, view=view)

    except discord.NotFound:
        app.logger.warning(f"Task message {task['message_id']} not found")
        # Clear message_id from task data
        tasks_data = data_manager_instance.load_guild_data(server_id, 'tasks')
        if str(task_id) in tasks_data['tasks']:
            tasks_data['tasks'][str(task_id)]['message_id'] = None
            data_manager_instance.save_guild_data(server_id, 'tasks', tasks_data)

    except Exception as e:
        app.logger.error(f"Error updating task message: {e}", exc_info=True)

@app.route('/api/<server_id>/tasks/<task_id>', methods=['DELETE'], endpoint='delete_server_task')
@jwt_required
def delete_server_task(server_id, task_id):
    """Delete task and remove Discord message"""
    try:
        tasks_data = data_manager_instance.load_guild_data(server_id, 'tasks')

        if task_id not in tasks_data.get('tasks', {}):
            return jsonify({'error': 'Task not found'}), 404

        task = tasks_data['tasks'][task_id]

        # Delete Discord message
        if 'message_id' in task and 'channel_id' in task:
            async def _delete_task_message():
                try:
                    guild = bot.get_guild(int(server_id))
                    if not guild:
                        return

                    channel = guild.get_channel(int(task['channel_id']))
                    if not channel:
                        return

                    message = await channel.fetch_message(int(task['message_id']))
                    await message.delete()
                    logger.info(f"Deleted task message {task['message_id']}")
                except discord.NotFound:
                    logger.warning(f"Task message {task['message_id']} already deleted")
                except Exception as e:
                    logger.error(f"Error deleting task message: {e}")

            try:
                future = asyncio.run_coroutine_threadsafe(
                    _delete_task_message(),
                    bot.loop
                )
                future.result(timeout=10)
            except Exception as e:
                logger.error(f"Failed to delete Discord message: {e}")

        # Remove from database
        del tasks_data['tasks'][task_id]

        # Clean up user_tasks
        if 'user_tasks' in tasks_data:
            for user_id in list(tasks_data['user_tasks'].keys()):
                if task_id in tasks_data['user_tasks'][user_id]:
                    del tasks_data['user_tasks'][user_id][task_id]

        data_manager_instance.save_guild_data(server_id, 'tasks', tasks_data)

        # Broadcast SSE
        sse_manager.broadcast_event('task_deleted', {
            'guild_id': server_id,
            'task_id': task_id
        })

        logger.info(f"Task deleted: {task_id} from guild {server_id}")

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error deleting task: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/transactions', methods=['GET'], endpoint='get_transactions')
def get_transactions(server_id):
    """Get transaction history for a server with advanced filtering"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)

        # Parse query parameters
        user_id = request.args.get('user_id')
        transaction_type = request.args.get('type')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        limit = min(int(request.args.get('limit', 100)), 500)  # Max 500
        offset = int(request.args.get('offset', 0))
        sort = request.args.get('sort', 'desc')

        # Parse dates
        start_date = None
        end_date = None
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'error': 'Invalid start_date format'}), 400
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'error': 'Invalid end_date format'}), 400

        # Create TransactionManager instance
        tm = TransactionManager(data_manager_instance)

        # Get filtered transactions
        result = tm.get_transactions(
            guild_id=guild_id,
            user_id=int(user_id) if user_id else None,
            transaction_type=transaction_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
            sort=sort
        )

        # Add user information if available
        bot_instance = get_bot()
        if bot_instance:
            guild = bot_instance.get_guild(guild_id)
            if guild:
                for txn in result['transactions']:
                    user_id_int = int(txn.get('user_id', 0))
                    member = guild.get_member(user_id_int)
                    if member:
                        txn['username'] = member.name
                        txn['display_name'] = member.display_name
                        txn['avatar_url'] = str(member.avatar.url) if member.avatar else None

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching transactions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/transactions/statistics', methods=['GET'], endpoint='get_transaction_statistics')
def get_transaction_statistics(server_id):
    """Get transaction statistics for a server"""
    if not data_manager_instance or not TransactionManager:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)
        user_id = request.args.get('user_id')
        period = request.args.get('period', 'all')

        # Validate period
        valid_periods = ['day', 'week', 'month', 'all']
        if period not in valid_periods:
            return jsonify({'error': 'Invalid period'}), 400

        # Create TransactionManager instance
        tm = TransactionManager(data_manager_instance)

        if user_id:
            # User-specific statistics
            stats = tm.get_user_statistics(guild_id, user_id, period)
        else:
            # Server-wide statistics
            stats = tm.get_server_statistics(guild_id, period)

        return jsonify(stats)

    except Exception as e:
        logger.error(f"Error fetching transaction statistics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/transactions/<transaction_id>', methods=['GET'], endpoint='get_transaction_detail')
def get_transaction_detail(server_id, transaction_id):
    """Get single transaction with full details"""
    if not data_manager_instance or not TransactionManager:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)

        # Create TransactionManager instance
        tm = TransactionManager(data_manager_instance)

        # Get all transactions and find the specific one
        result = tm.get_transactions(guild_id=guild_id, limit=10000)  # Get many to find the specific one

        for txn in result['transactions']:
            if txn['id'] == transaction_id:
                # Add user information if available
                bot_instance = get_bot()
                if bot_instance:
                    guild = bot_instance.get_guild(guild_id)
                    if guild:
                        user_id_int = int(txn.get('user_id', 0))
                        member = guild.get_member(user_id_int)
                        if member:
                            txn['username'] = member.name
                            txn['display_name'] = member.display_name
                            txn['avatar_url'] = str(member.avatar.url) if member.avatar else None

                return jsonify(txn)

        return jsonify({'error': 'Transaction not found'}), 404

    except Exception as e:
        logger.error(f"Error fetching transaction detail: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/transactions/validate', methods=['POST'], endpoint='validate_user_transactions')
def validate_user_transactions(server_id):
    """Validate transaction integrity for a user"""
    if not data_manager_instance or not TransactionManager:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        data = request.get_json()
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id is required'}), 400

        guild_id = int(server_id)

        # Create TransactionManager instance
        tm = TransactionManager(data_manager_instance)

        # Validate transaction integrity
        validation_result = tm.validate_transaction_integrity(guild_id, user_id)

        return jsonify(validation_result)

    except Exception as e:
        logger.error(f"Error validating transactions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/transactions/export', methods=['GET'], endpoint='export_transactions')
def export_transactions(server_id):
    """Export transactions as CSV with filtering"""
    if not data_manager_instance or not TransactionManager:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)

        # Parse query parameters for filtering
        user_id = request.args.get('user_id')
        transaction_type = request.args.get('type')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        # Parse dates
        start_date = None
        end_date = None
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'error': 'Invalid start_date format'}), 400
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'error': 'Invalid end_date format'}), 400

        # Create TransactionManager instance
        tm = TransactionManager(data_manager_instance)

        # Get filtered transactions (no limit for export)
        result = tm.get_transactions(
            guild_id=guild_id,
            user_id=user_id,
            transaction_type=transaction_type,
            start_date=start_date,
            end_date=end_date,
            limit=10000  # Reasonable limit for export
        )

        # Create CSV
        import io
        import csv

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'id', 'user_id', 'username', 'amount', 'balance_before', 'balance_after',
            'type', 'description', 'timestamp', 'source'
        ])
        writer.writeheader()

        # Add user information
        bot_instance = get_bot()
        user_cache = {}
        if bot_instance:
            guild = bot_instance.get_guild(guild_id)
            if guild:
                for member in guild.members:
                    user_cache[str(member.id)] = member.name

        for txn in result['transactions']:
            writer.writerow({
                'id': txn.get('id', ''),
                'user_id': txn.get('user_id', ''),
                'username': user_cache.get(txn.get('user_id', ''), ''),
                'amount': txn.get('amount', 0),
                'balance_before': txn.get('balance_before', 0),
                'balance_after': txn.get('balance_after', 0),
                'type': txn.get('type', ''),
                'description': txn.get('description', ''),
                'timestamp': txn.get('timestamp', ''),
                'source': txn.get('metadata', {}).get('source', 'discord')
            })

        output.seek(0)

        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=transactions_{server_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )

    except Exception as e:
        logger.error(f"Error exporting transactions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/transactions/archive', methods=['POST'], endpoint='archive_old_transactions')
def archive_old_transactions(server_id):
    """Archive old transactions (older than specified days)"""
    if not data_manager_instance or not TransactionManager:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)
        data = request.get_json() or {}
        days_to_keep = data.get('days_to_keep', 90)
        archive = data.get('archive', True)

        # Create TransactionManager instance
        tm = TransactionManager(data_manager_instance)

        # Get transaction counts before archiving
        before_count = len(tm.get_transactions(guild_id)['transactions'])

        # Perform archiving
        tm.cleanup_old_transactions(guild_id, days_to_keep, archive)

        # Get transaction counts after archiving
        after_count = len(tm.get_transactions(guild_id)['transactions'])
        archived_count = before_count - after_count

        log_event('info', f'Archived {archived_count} old transactions for server {server_id} (kept last {days_to_keep} days)')

        return jsonify({
            'success': True,
            'archived_count': archived_count,
            'remaining_count': after_count,
            'days_kept': days_to_keep,
            'archived': archive
        })

    except Exception as e:
        logger.error(f"Error archiving transactions: {e}")
        return jsonify({'error': str(e)}), 500

# === USER MANAGEMENT ===

@app.route('/api/<server_id>/users/cleanup', methods=['POST'], endpoint='cleanup_inactive_users')
def cleanup_inactive_users(server_id):
    """Clean up inactive users who haven't been seen for X days"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)
        data = request.get_json() or {}
        days = data.get('days', 30)

        if days < 7:
            return jsonify({'error': 'Days must be at least 7 for safety'}), 400

        # Get all users from currency data
        currency_data = data_manager_instance.load_guild_data(guild_id, 'currency')
        users = currency_data.get('users', {})

        # Find inactive users
        cutoff_date = datetime.now() - timedelta(days=days)
        inactive_users = []

        for user_id, user_data in users.items():
            if user_data.get('is_active', True):
                continue  # Skip active users

            left_at = user_data.get('left_at')
            if not left_at:
                continue  # No leave date recorded

            try:
                leave_date = datetime.fromisoformat(left_at)
                if leave_date < cutoff_date:
                    inactive_users.append((user_id, user_data))
            except (ValueError, TypeError):
                continue  # Invalid date format

        if not inactive_users:
            return jsonify({
                'success': True,
                'message': f'No inactive users found who left more than {days} days ago',
                'removed_count': 0,
                'removed_balance': 0
            })

        # Create backup
        backup_data = {
            'inactive_users': inactive_users,
            'cleanup_date': datetime.now().isoformat(),
            'cleanup_by': 'web_dashboard',
            'days_threshold': days
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        data_manager_instance.save_guild_data(guild_id, f"inactive_users_backup_{timestamp}", backup_data)

        # Remove inactive users
        removed_count = 0
        removed_balance = 0

        for user_id, user_data in inactive_users:
            balance = user_data.get('balance', 0)
            removed_balance += balance

            # Remove from users
            del currency_data['users'][user_id]

            # Remove from inventory
            inventory = currency_data.get('inventory', {})
            if user_id in inventory:
                del inventory[user_id]

            removed_count += 1

        # Update total currency
        currency_data['metadata']['total_currency'] = sum(
            u.get('balance', 0) for u in currency_data['users'].values()
        )

        # Save cleaned data
        data_manager_instance.save_guild_data(guild_id, 'currency', currency_data)

        # Broadcast SSE event
        sse_manager.broadcast_event('users_cleaned', {
            'guild_id': guild_id,
            'removed_count': removed_count,
            'removed_balance': removed_balance,
            'days_threshold': days
        })

        log_event('info', f'Cleaned up {removed_count} inactive users from server {server_id} (balance recovered: {removed_balance})')

        return jsonify({
            'success': True,
            'removed_count': removed_count,
            'removed_balance': removed_balance,
            'days_threshold': days,
            'backup_file': f"inactive_users_backup_{timestamp}"
        })

    except Exception as e:
        logger.error(f"Error cleaning up inactive users: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/users/inactive', endpoint='get_inactive_users')
def get_inactive_users(server_id):
    """Get list of inactive users"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)
        data = request.get_json() or {}
        days = data.get('days', 30)

        cutoff_date = datetime.now() - timedelta(days=days)

        # Get all users from currency data
        currency_data = data_manager_instance.load_guild_data(guild_id, 'currency')
        users = currency_data.get('users', {})

        inactive_users = []

        for user_id, user_data in users.items():
            if user_data.get('is_active', True):
                continue  # Skip active users

            left_at = user_data.get('left_at')
            if not left_at:
                continue  # No leave date recorded

            try:
                leave_date = datetime.fromisoformat(left_at)
                if leave_date < cutoff_date:
                    inactive_users.append({
                        'user_id': user_id,
                        'balance': user_data.get('balance', 0),
                        'left_at': left_at,
                        'days_since_left': (datetime.now() - leave_date).days,
                        'username': user_data.get('username', 'Unknown'),
                        'discriminator': user_data.get('discriminator', '0000')
                    })
            except (ValueError, TypeError):
                continue  # Invalid date format

        # Sort by days since left (most recent first)
        inactive_users.sort(key=lambda x: x['days_since_left'])

        return jsonify({
            'inactive_users': inactive_users,
            'total_count': len(inactive_users),
            'days_threshold': days
        })

    except Exception as e:
        logger.error(f"Error getting inactive users: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/users/reactivate/<user_id>', methods=['POST'], endpoint='reactivate_user')
def reactivate_user(server_id, user_id):
    """Reactivate a previously inactive user"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)

        # Load currency data
        currency_data = data_manager_instance.load_guild_data(guild_id, 'currency')
        users = currency_data.get('users', {})

        if user_id not in users:
            return jsonify({'error': 'User not found'}), 404

        user_data = users[user_id]

        if user_data.get('is_active', True):
            return jsonify({'error': 'User is already active'}), 400

        # Reactivate user
        user_data['is_active'] = True
        user_data['reactivated_at'] = datetime.now().isoformat()
        del user_data['left_at']  # Remove leave date

        # Save data
        data_manager_instance.save_guild_data(guild_id, 'currency', currency_data)

        # Broadcast SSE event
        sse_manager.broadcast_event('user_reactivated', {
            'guild_id': guild_id,
            'user_id': user_id,
            'balance': user_data.get('balance', 0)
        })

        log_event('info', f'Reactivated user {user_id} in server {server_id}')

        return jsonify({
            'success': True,
            'user_id': user_id,
            'balance': user_data.get('balance', 0)
        })

    except Exception as e:
        logger.error(f"Error reactivating user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/users/inactive', methods=['GET'], endpoint='get_inactive_users_list')
@session_required
def get_inactive_users_list(server_id):
    """Get list of inactive users with optional days filter"""
    try:
        bot_instance = get_bot()
        if not bot_instance:
            return jsonify({'error': 'Bot not ready'}), 503

        guild = bot_instance.get_guild(int(server_id))
        if not guild:
            return jsonify({'error': 'Server not found'}), 404

        # Get inactivity threshold from guild config
        config_result = data_manager_instance.supabase.table('guilds').select('inactivity_days').eq('guild_id', server_id).execute()
        inactivity_days = config_result.data[0].get('inactivity_days', 30) if config_result.data else 30

        # Get inactive users from database
        result = data_manager_instance.supabase.table('users').select(
            'user_id, balance, total_earned, total_spent, updated_at'
        ).eq('guild_id', server_id).eq('is_active', False).execute()

        inactive_users = []
        for user_data in result.data:
            try:
                member = guild.get_member(int(user_data['user_id']))
                inactive_users.append({
                    'user_id': user_data['user_id'],
                    'username': member.name if member else f"User {user_data['user_id']}",
                    'balance': user_data['balance'],
                    'total_earned': user_data['total_earned'],
                    'total_spent': user_data['total_spent'],
                    'last_activity': user_data['updated_at']
                })
            except Exception as e:
                logger.error(f"Error fetching member {user_data['user_id']}: {e}")
                continue

        return jsonify({
            'inactive_users': inactive_users,
            'threshold_days': inactivity_days,
            'count': len(inactive_users)
        })

    except Exception as e:
        logger.error(f"Error fetching inactive users: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/users/reactivate/<user_id>', methods=['POST'], endpoint='reactivate_user_db')
@session_required
def reactivate_user_db(server_id, user_id):
    """Reactivate an inactive user"""
    try:
        # Update user to active status
        result = data_manager_instance.supabase.table('users').update({
            'is_active': True,
            'updated_at': datetime.utcnow().isoformat()
        }).eq('guild_id', server_id).eq('user_id', user_id).execute()

        if not result.data:
            return jsonify({'error': 'User not found'}), 404

        # Broadcast SSE update
        sse_manager.broadcast_event('user.reactivated', {
            'guild_id': server_id,
            'user_id': user_id
        })

        return jsonify({'success': True, 'message': 'User reactivated'})

    except Exception as e:
        logger.error(f"Error reactivating user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/config', methods=['PUT'], endpoint='update_server_config_db')
@session_required
def update_server_config_db(server_id):
    """Update server configuration including inactivity_days"""
    try:
        data = request.get_json()

        # Build update dict with only provided fields
        updates = {}
        if 'inactivity_days' in data:
            inactivity_days = int(data['inactivity_days'])
            if inactivity_days < 1:
                return jsonify({'error': 'inactivity_days must be positive'}), 400
            updates['inactivity_days'] = inactivity_days

        # Add other config fields as needed
        if 'currency_name' in data:
            updates['currency_name'] = data['currency_name']
        if 'currency_symbol' in data:
            updates['currency_symbol'] = data['currency_symbol']

        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400

        updates['updated_at'] = datetime.utcnow().isoformat()

        # Update database
        result = data_manager_instance.supabase.table('guilds').update(updates).eq('guild_id', server_id).execute()

        if not result.data:
            return jsonify({'error': 'Server not found'}), 404

        # Invalidate cache
        data_manager_instance.cache_manager.invalidate_cache(server_id, 'config')

        # Broadcast update
        sse_manager.broadcast_event('config.updated', {
            'guild_id': server_id,
            'updates': updates
        })

        return jsonify({'success': True, 'config': result.data[0]})

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({'error': str(e)}), 500

# Announcement API endpoints
@app.route('/api/<server_id>/announcements', methods=['GET'], endpoint='get_announcements')
def get_announcements(server_id):
    """Get all announcements for server"""
    try:
        ann_data = data_manager_instance.load_guild_data(server_id, "announcements")
        if not ann_data:
            return jsonify({"announcements": [], "task_announcements": {}})

        return jsonify(ann_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/<server_id>/announcements', methods=['POST'], endpoint='create_announcement_api')
def create_announcement_api(server_id):
    """Create announcement via API"""
    try:
        data = request.json

        # Validate required fields
        required = ['title', 'content', 'channel_id', 'author_id', 'author_name']
        if not all(field in data for field in required):
            return jsonify({"error": "Missing required fields"}), 400

        # Get bot instance
        if not bot:
            return jsonify({"error": "Bot not ready"}), 503

        # Create announcement asynchronously
        future = asyncio.run_coroutine_threadsafe(
            bot.get_cog('Announcements').announcement_manager.create_announcement(
                guild_id=server_id,
                title=data['title'],
                content=data['content'],
                channel_id=data['channel_id'],
                author_id=data['author_id'],
                author_name=data['author_name'],
                announcement_type=data.get('type', 'general'),
                mentions=data.get('mentions', {"everyone": False, "roles": [], "users": []}),
                embed_color=data.get('embed_color', '#5865F2'),
                thumbnail=data.get('thumbnail'),
                auto_pin=data.get('auto_pin', False)
            ),
            bot.loop
        )

        announcement = future.result(timeout=10)
        return jsonify(announcement), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/<server_id>/announcements/task/<task_id>', methods=['POST'], endpoint='create_task_announcement_api')
def create_task_announcement_api(server_id, task_id):
    """Create task announcement via API"""
    try:
        data = request.json or {}

        if not bot:
            return jsonify({"error": "Bot not ready"}), 503

        # Create task announcement
        future = asyncio.run_coroutine_threadsafe(
            bot.get_cog('Announcements').announcement_manager.create_task_announcement(
                guild_id=server_id,
                task_id=task_id,
                channel_id=data.get('channel_id'),
                author_id=data.get('author_id', 'system'),
                author_name=data.get('author_name', 'System'),
                auto_pin=data.get('auto_pin')
            ),
            bot.loop
        )

        announcement = future.result(timeout=10)
        return jsonify(announcement), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/<server_id>/announcements/<announcement_id>', methods=['PUT'], endpoint='edit_announcement_api')
def edit_announcement_api(server_id, announcement_id):
    """Edit announcement via API"""
    try:
        data = request.json

        if not bot:
            return jsonify({"error": "Bot not ready"}), 503

        future = asyncio.run_coroutine_threadsafe(
            bot.get_cog('Announcements').announcement_manager.edit_announcement(
                guild_id=server_id,
                announcement_id=announcement_id,
                title=data.get('title'),
                content=data.get('content'),
                embed_color=data.get('embed_color')
            ),
            bot.loop
        )

        announcement = future.result(timeout=10)
        return jsonify(announcement)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/<server_id>/announcements/<announcement_id>', methods=['DELETE'], endpoint='delete_announcement_api')
def delete_announcement_api(server_id, announcement_id):
    """Delete announcement via API"""
    try:
        data = request.json or {}
        delete_discord = data.get('delete_discord_message', True)

        if not bot:
            return jsonify({"error": "Bot not ready"}), 503

        future = asyncio.run_coroutine_threadsafe(
            bot.get_cog('Announcements').announcement_manager.delete_announcement(
                guild_id=server_id,
                announcement_id=announcement_id,
                delete_discord_message=delete_discord
            ),
            bot.loop
        )

        success = future.result(timeout=10)
        return jsonify({"success": success})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/<server_id>/announcements/<announcement_id>/pin', methods=['POST'], endpoint='pin_announcement_api')
def pin_announcement_api(server_id, announcement_id):
    """Pin announcement via API"""
    try:
        if not bot:
            return jsonify({"error": "Bot not ready"}), 503

        future = asyncio.run_coroutine_threadsafe(
            bot.get_cog('Announcements').announcement_manager.pin_announcement(
                guild_id=server_id,
                announcement_id=announcement_id
            ),
            bot.loop
        )

        success = future.result(timeout=10)
        return jsonify({"success": success})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/<server_id>/announcements/<announcement_id>/unpin', methods=['POST'], endpoint='unpin_announcement_api')
def unpin_announcement_api(server_id, announcement_id):
    """Unpin announcement via API"""
    try:
        if not bot:
            return jsonify({"error": "Bot not ready"}), 503

        future = asyncio.run_coroutine_threadsafe(
            bot.get_cog('Announcements').announcement_manager.unpin_announcement(
                guild_id=server_id,
                announcement_id=announcement_id
            ),
            bot.loop
        )

        success = future.result(timeout=10)
        return jsonify({"success": success})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === EMBEDS ===

@app.route('/api/<server_id>/embeds', methods=['GET'], endpoint='get_embeds')
def get_embeds(server_id):
    """Get all embeds for a server"""
    try:
        guild_id = int(server_id)
        embeds_data = data_manager_instance.load_guild_data(guild_id, 'embeds')

        if not embeds_data:
            embeds_data = {'embeds': {}, 'templates': {}, 'settings': {}}

        return jsonify(embeds_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/embeds/<embed_id>', methods=['PUT'], endpoint='update_embed')
def update_embed(server_id, embed_id):
    """Update an existing embed"""
    try:
        guild_id = int(server_id)
        data = request.json

        embeds_data = data_manager_instance.load_guild_data(guild_id, 'embeds')
        if not embeds_data or embed_id not in embeds_data.get('embeds', {}):
            return jsonify({'error': 'Embed not found'}), 404

        embed_data = embeds_data['embeds'][embed_id]

        # Update fields
        for key in ['title', 'description', 'color', 'thumbnail_url', 'image_url',
                    'footer_text', 'footer_icon_url', 'author_name', 'author_icon_url', 'fields']:
            if key in data:
                embed_data[key] = data[key]

        embed_data['updated_at'] = datetime.now().isoformat()

        # Validate
        from core.embed_builder import EmbedBuilder
        valid, error = EmbedBuilder.validate_embed_data(embed_data)
        if not valid:
            return jsonify({'error': error}), 400

        # Update Discord message
        async def _update_embed_message():
            guild = bot_instance.get_guild(guild_id)
            if not guild:
                return False

            channel = guild.get_channel(int(embed_data['channel_id']))
            if not channel:
                return False

            try:
                message = await channel.fetch_message(int(embed_data['message_id']))
                new_embed = EmbedBuilder.build_embed(embed_data)
                await message.edit(embed=new_embed)
                return True
            except Exception as e:
                print(f"Error updating embed: {e}")
                return False

        future = asyncio.run_coroutine_threadsafe(
            _update_embed_message(),
            bot_instance.loop
        )

        try:
            success = future.result(timeout=10)
            if not success:
                return jsonify({'error': 'Failed to update Discord message'}), 500
        except Exception as e:
            return jsonify({'error': f'Discord error: {str(e)}'}), 500

        # Save to database
        data_manager_instance.save_guild_data(guild_id, 'embeds', embeds_data)

        return jsonify({
            'success': True,
            'embed': embed_data
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/embeds/<embed_id>', methods=['DELETE'], endpoint='delete_embed')
def delete_embed(server_id, embed_id):
    """Delete an embed"""
    try:
        guild_id = int(server_id)

        embeds_data = data_manager_instance.load_guild_data(guild_id, 'embeds')
        if not embeds_data or embed_id not in embeds_data.get('embeds', {}):
            return jsonify({'error': 'Embed not found'}), 404

        embed_data = embeds_data['embeds'][embed_id]

        # Delete Discord message
        async def _delete_embed_message():
            guild = bot_instance.get_guild(guild_id)
            if not guild:
                return True  # Continue with DB deletion

            channel = guild.get_channel(int(embed_data['channel_id']))
            if not channel:
                return True

            try:
                message = await channel.fetch_message(int(embed_data['message_id']))
                await message.delete()
            except discord.NotFound:
                pass  # Already deleted
            except Exception as e:
                print(f"Error deleting embed message: {e}")

            return True

        future = asyncio.run_coroutine_threadsafe(
            _delete_embed_message(),
            bot_instance.loop
        )
        future.result(timeout=10)

        # Remove from database
        del embeds_data['embeds'][embed_id]
        data_manager_instance.save_guild_data(guild_id, 'embeds', embeds_data)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/channels', methods=['GET'], endpoint='get_channels')
def get_channels(server_id):
    """Get text channels for a server"""
    try:
        guild_id = int(server_id)
        guild = bot_instance.get_guild(guild_id)

        if not guild:
            return jsonify({'error': 'Server not found'}), 404

        channels = []
        for channel in guild.text_channels:
            channels.append({
                'id': str(channel.id),
                'name': channel.name,
                'type': 'text',
                'position': channel.position
            })

        channels.sort(key=lambda x: x['position'])

        return jsonify(channels)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export', endpoint='export_data')
def export_data():
    data = {
        'status': read_json_file(STATUS_FILE),
        'settings': read_json_file(SETTINGS_FILE),
        'commands': read_json_file(COMMANDS_FILE),
        'tasks': read_json_file(TASKS_FILE),
        'logs': read_json_file(LOGS_FILE),
        'exported_at': datetime.now().isoformat()
    }
    return jsonify(data)

# Enhanced SSE system with batching and selective subscriptions
class SSEManager:
    def __init__(self):
        self.clients = {}  # client_id -> queue
        self.subscriptions = {}  # client_id -> {'guilds': set, 'event_types': set}
        self.event_buffer = defaultdict(list)  # event_type -> [events]
        self.buffer_lock = threading.Lock()
        self.batch_timer = None
        self.keepalive_timer = None
        self.BATCH_INTERVAL = 0.5  # Send batches every 500ms
        self.MAX_BATCH_SIZE = 10  # Maximum events per batch
        self.KEEPALIVE_INTERVAL = 30  # Send keepalive every 30 seconds

        # Start batch processing timer
        self._start_batch_timer()
        # Start keepalive timer
        self._start_keepalive_timer()

    def _start_batch_timer(self):
        """Start timer for batch processing"""
        def process_batches():
            while True:
                time_module.sleep(self.BATCH_INTERVAL)
                self._process_event_batches()

        self.batch_timer = threading.Thread(target=process_batches, daemon=True)
        self.batch_timer.start()

    def _start_keepalive_timer(self):
        """Start timer for sending keepalive messages to SSE clients"""
        def send_keepalive():
            while True:
                time_module.sleep(self.KEEPALIVE_INTERVAL)
                self._send_keepalive_messages()

        self.keepalive_timer = threading.Thread(target=send_keepalive, daemon=True)
        self.keepalive_timer.start()

    def _send_keepalive_messages(self):
        """Send keepalive ping to all connected SSE clients"""
        disconnected_clients = []

        for client_id in list(self.clients.keys()):
            try:
                # Send keepalive ping
                keepalive_event = {
                    'type': 'keepalive',
                    'timestamp': time_module.time(),
                    'message': 'Connection active'
                }
                self.clients[client_id].put(keepalive_event, timeout=1)  # Non-blocking with timeout
            except queue.Full:
                # Client queue is full, mark for disconnection
                disconnected_clients.append(client_id)
            except Exception as e:
                # Client likely disconnected
                logger.debug(f"SSE keepalive failed for client {client_id}: {e}")
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            logger.debug(f"Removing disconnected SSE client: {client_id}")
            self.unsubscribe_client(client_id)

    def _process_event_batches(self):
        """Process and send batched events"""
        with self.buffer_lock:
            for event_type, events in self.event_buffer.items():
                if not events:
                    continue

                # Group events by guild for selective subscriptions
                guild_events = defaultdict(list)
                for event in events:
                    guild_id = event.get('guild_id', 'global')
                    guild_events[guild_id].append(event)

                # Send batched events to subscribed clients
                for guild_id, guild_event_list in guild_events.items():
                    # Find subscribed clients for this guild and event type
                    subscribed_clients = []
                    for client_id, sub in self.subscriptions.items():
                        if not sub['guilds'] or guild_id in sub['guilds']:
                            if not sub['event_types'] or event_type in sub['event_types']:
                                subscribed_clients.append(client_id)

                    # Send to subscribed clients
                    for client_id in subscribed_clients:
                        if client_id in self.clients:
                            try:
                                if len(guild_event_list) == 1:
                                    # Single event
                                    self.clients[client_id].put(guild_event_list[0])
                                else:
                                    # Batched events
                                    batch_event = {
                                        'type': 'batch',
                                        'event_type': event_type,
                                        'guild_id': guild_id,
                                        'events': guild_event_list,
                                        'timestamp': time_module.time()
                                    }
                                    self.clients[client_id].put(batch_event)
                            except:
                                # Client disconnected
                                self.unsubscribe_client(client_id)

                # Clear processed events
                self.event_buffer[event_type].clear()

    def broadcast_event(self, event_type, event_data):
        """Broadcast event with batching support"""
        with self.buffer_lock:
            self.event_buffer[event_type].append({
                **event_data,
                'timestamp': time_module.time()
            })

            # If buffer gets too large, process immediately
            if len(self.event_buffer[event_type]) >= self.MAX_BATCH_SIZE:
                self._process_event_batches()

    def subscribe_client(self, client_id, guilds=None, event_types=None):
        """Subscribe client to specific guilds and event types"""
        self.subscriptions[client_id] = {
            'guilds': set(guilds or []),
            'event_types': set(event_types or []),
            'connected_at': time_module.time()
        }
        self.clients[client_id] = queue.Queue()

    def unsubscribe_client(self, client_id):
        """Unsubscribe client"""
        self.subscriptions.pop(client_id, None)
        self.clients.pop(client_id, None)

    def get_client_queue(self, client_id):
        """Get event queue for a client"""
        return self.clients.get(client_id)

    def get_subscribed_clients(self, guild_id, event_type):
        """Get clients subscribed to specific guild and event type"""
        subscribed = []
        for client_id, sub in self.subscriptions.items():
            if not sub['guilds'] or guild_id in sub['guilds']:
                if not sub['event_types'] or event_type in sub['event_types']:
                    subscribed.append(client_id)
        return subscribed

# Global SSE manager instance
sse_manager = SSEManager()

@app.route('/api/stream', endpoint='stream')
def stream():
    """Enhanced Server-Sent Events endpoint with selective subscriptions"""
    # Parse subscription parameters
    subscribed_guilds = request.args.get('guilds', '').split(',') if request.args.get('guilds') else None
    subscribed_events = request.args.get('events', '').split(',') if request.args.get('events') else None

    # Generate client ID for tracking
    client_id = f"client_{int(time_module.time() * 1000)}_{hash(request.remote_addr) % 10000}"

    # Subscribe client
    sse_manager.subscribe_client(client_id, subscribed_guilds, subscribed_events)

    def generate():
        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'client_id': client_id})}\n\n"

            client_queue = sse_manager.get_client_queue(client_id)
            if not client_queue:
                return

            while True:
                try:
                    # Wait for events with timeout for heartbeat
                    event = client_queue.get(timeout=30)

                    # Event is already filtered by SSEManager, just send it
                    yield f"data: {json.dumps(event)}\n\n"

                except queue.Empty:
                    # Send heartbeat with connection info
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time_module.time()})}\n\n"

        except GeneratorExit:
            # Client disconnected
            sse_manager.unsubscribe_client(client_id)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': '*'
        }
    )

@app.route('/api/stream/test', methods=['POST'], endpoint='test_sse')
def test_sse():
    """Test endpoint to send SSE events"""
    event_type = request.json.get('event_type', 'test')
    event_data = request.json.get('data', {})

    sse_manager.broadcast_event(event_type, event_data)

    return jsonify({'success': True, 'event_type': event_type})

# Register data manager listener to broadcast updates
def broadcast_update(event_type, data):
    """Broadcast updates to all SSE clients"""
    try:
        if event_type == 'guild_update':
            # Handle standard guild data updates
            sse_manager.broadcast_event('guild_update', {
                'guild_id': str(data.get('guild_id', '')),
                'type': data.get('data_type', 'unknown'),
                'action': 'update',
                'timestamp': time_module.time()
            })
        elif event_type in ['shop_update', 'inventory_update']:
            # Handle shop-specific events
            sse_manager.broadcast_event(event_type, {
                'guild_id': str(data.get('guild_id', '')),
                'action': data.get('action', 'update'),
                'item_id': data.get('item_id'),
                'user_id': data.get('user_id'),
                'timestamp': time_module.time()
            })
        else:
            # Handle other event types generically
            sse_manager.broadcast_event(event_type, {
                'guild_id': str(data.get('guild_id', '')),
                'action': 'update',
                'data': data,
                'timestamp': time_module.time()
            })
    except Exception as e:
        logger.error(f"Error broadcasting update: {e}")

# Connect to data manager when available
def init_sse():
    if data_manager_instance and hasattr(data_manager_instance, 'register_listener'):
        data_manager_instance.register_listener(broadcast_update)
        logger.info("SSE broadcast system initialized")

# Call after data_manager_instance is set
init_sse()

def set_bot_instance(bot_instance):
    """Set the bot instance for API access"""
    global bot
    bot = bot_instance
    logger.info("Bot instance set in backend")

def set_data_manager(dm_instance):
    """Set the data manager instance"""
    global data_manager_instance
    data_manager_instance = dm_instance
    print(f"DEBUG: set_data_manager called with {dm_instance}")

    # Test database connection before proceeding
    try:
        logger.info("Testing database connection...")
        # Test connection by getting connection status
        connection_status = data_manager_instance.get_connection_status()
        if not connection_status.get('healthy'):
            logger.error("❌ Database connection test failed!")
            logger.error(f"Connection status: {connection_status}")
            sys.exit(1)
        logger.info("✅ Database connection test passed")
    except Exception as e:
        logger.error(f"❌ Database connection test failed: {e}")
        sys.exit(1)

    # Register SSE broadcaster
    if hasattr(data_manager_instance, 'register_listener'):
        data_manager_instance.register_listener(broadcast_update)
        logger.info("SSE broadcaster registered with data manager")

def run_backend():
    """Run the Flask backend server"""
    try:
        # Start bot in separate thread before Flask starts
        start_bot_thread()

        # Use PORT environment variable for Railway deployment, default to 5000 for local development
        port = int(os.getenv('PORT', 5000))

        flask_env = os.getenv('FLASK_ENV', 'development')
        debug_mode = flask_env == 'development'
        logger.info(f"Starting Flask backend on http://0.0.0.0:{port} (FLASK_ENV={flask_env}, debug={debug_mode})")
        app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"Error starting backend: {e}")

# Utility functions
def check_bot_running():
    """Check if the bot process is running"""
    # Check if bot instance is available and connected
    try:
        bot_instance = get_bot()
        if bot_instance:
            # Check if bot is ready
            if hasattr(bot_instance, 'is_ready') and bot_instance.is_ready():
                return True
            # Also check if bot has guilds (indicates it's connected)
            if hasattr(bot_instance, 'guilds') and len(bot_instance.guilds) > 0:
                return True
        return False
    except:
        return False

def kill_bot_process():
    """Kill the bot process if running"""
    # Simplified version without psutil
    try:
        import subprocess
        subprocess.run(['taskkill', '/F', '/IM', 'python.exe'], capture_output=True)
    except:
        pass

def calculate_uptime():
    """Calculate bot uptime in seconds"""
    # This is a simplified version - in a real implementation,
    # you'd track the actual start time
    return 3600  # Placeholder: 1 hour

# TaskClaimView class for Discord UI components
class TaskClaimView(View):
    """Persistent view for task claim button."""

    def __init__(self, task_id):
        super().__init__(timeout=None)
        self.task_id = task_id

    @discord.ui.button(
        label="Claim Task",
        style=discord.ButtonStyle.green,
        custom_id="claim_task",
        emoji="✋"
    )
    async def claim_button(self, interaction: discord.Interaction, button: Button):
        await self.handle_claim(interaction)

    async def handle_claim(self, interaction: discord.Interaction):
        """Handle task claim with atomic operations to prevent race conditions."""
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        task_id = str(self.task_id)

        try:
            # Use atomic task claim operation
            result = await self.atomic_task_claim(guild_id, user_id, task_id)

            if not result['success']:
                await interaction.followup.send(result['error'], ephemeral=True)
                return

            # Update embed
            await self.update_task_message(interaction.guild, guild_id, self.task_id, result['task'])

            # Notify user
            embed = discord.Embed(
                title="✅ Task Claimed Successfully!",
                description=f"You have claimed **{result['task']['name']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="⏰ Deadline", value=f"<t:{int(result['deadline'].timestamp())}:R>", inline=False)
            embed.add_field(
                name="📝 Submit Proof",
                value="Use `/task submit` command with proof of completion",
                inline=False
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Broadcast SSE event for real-time updates
            sse_manager.broadcast_event('task_update', {
                'guild_id': guild_id,
                'task_id': task_id,
                'action': 'claimed',
                'user_id': user_id,
                'current_claims': result['task']['current_claims'],
                'status': result['task']['status']
            })

        except Exception as e:
            app.logger.error(f"Task claim error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while claiming the task. Please try again.",
                ephemeral=True
            )

    async def atomic_task_claim(self, guild_id, user_id, task_id):
        """Atomically claim a task with proper validation and race condition prevention."""

        def claim_task_operation(tasks_data, currency_data):
            task = tasks_data.get('tasks', {}).get(task_id)

            if not task:
                return {'success': False, 'error': "❌ Task not found."}

            # Validation checks
            if task['status'] != 'active':
                return {'success': False, 'error': f"❌ This task is no longer active (Status: {task['status']})."}

            # Check expiry
            if datetime.now(timezone.utc) > datetime.fromisoformat(task['expires_at']):
                # Auto-expire task
                task['status'] = 'expired'
                tasks_data['metadata']['total_expired'] = tasks_data.get('metadata', {}).get('total_expired', 0) + 1
                return {'success': False, 'error': "❌ This task has expired."}

            # Check max claims
            if task['max_claims'] != -1 and task['current_claims'] >= task['max_claims']:
                return {'success': False, 'error': "❌ This task has reached maximum claims."}

            # Check if user already claimed
            user_tasks = tasks_data.get('user_tasks', {}).get(user_id, {})
            if task_id in user_tasks:
                status = user_tasks[task_id]['status']
                return {'success': False, 'error': f"❌ You have already claimed this task (Status: {status})."}

            # Check user task limit
            settings = tasks_data.get('settings', {})
            max_per_user = settings.get('max_tasks_per_user', 10)
            active_count = sum(
                1 for t in user_tasks.values()
                if t['status'] in ['claimed', 'in_progress', 'submitted']
            )
            if active_count >= max_per_user:
                return {'success': False, 'error': f"❌ You have reached the maximum of {max_per_user} active tasks."}

            # Claim task
            claimed_at = datetime.now(timezone.utc)
            deadline = claimed_at + timedelta(hours=task['duration_hours'])

            tasks_data.setdefault('user_tasks', {}).setdefault(user_id, {})[task_id] = {
                'claimed_at': claimed_at.isoformat(),
                'deadline': deadline.isoformat(),
                'status': 'in_progress',
                'proof_message_id': None,
                'proof_attachments': [],
                'proof_content': '',
                'submitted_at': None,
                'completed_at': None,
                'notes': ''
            }

            # Update task claims
            task['current_claims'] += 1
            task['assigned_users'].append(user_id)

            return {
                'success': True,
                'task': task,
                'deadline': deadline,
                'claimed_at': claimed_at
            }

        # Execute atomic operation
        try:
            result = atomic_task_operation(guild_id, claim_task_operation)
            return result
        except Exception as e:
            app.logger.error(f"Atomic task claim failed: {e}", exc_info=True)
            return {'success': False, 'error': "❌ An error occurred while claiming the task. Please try again."}

    async def expire_task(self, guild_id, task_id, guild):
        """Mark task as expired and update message."""
        tasks_data = data_manager_instance.load_guild_data(guild_id, 'tasks')
        task = tasks_data['tasks'].get(str(task_id))

        if task:
            task['status'] = 'expired'
            tasks_data['metadata']['total_expired'] = tasks_data.get('metadata', {}).get('total_expired', 0) + 1
            data_manager_instance.save_guild_data(guild_id, 'tasks', tasks_data)

            await self.update_task_message(guild, guild_id, task_id, task)

    async def update_task_message(self, guild, guild_id, task_id, task):
        """Update Discord task message with current data."""
        if not task.get('message_id'):
            return

        try:
            channel = guild.get_channel(int(task['channel_id']))
            if not channel:
                return

            message = await channel.fetch_message(int(task['message_id']))
            embed = create_task_embed(task)

            # Disable button if task is not active
            view = None if task['status'] != 'active' else TaskClaimView(task_id)

            await message.edit(embed=embed, view=view)

        except discord.NotFound:
            app.logger.warning(f"Task message {task['message_id']} not found")
        except Exception as e:
            app.logger.error(f"Error updating task message: {e}", exc_info=True)

def run_discord_task(coro):
    """Helper to run Discord coroutine from sync context."""
    bot_instance = get_bot()
    if not bot_instance:
        raise Exception("Bot not available")
    future = asyncio.run_coroutine_threadsafe(coro, bot_instance.loop)
    return future.result(timeout=10)

def await_coroutine(coro):
    """Helper to run coroutine from sync context."""
    return run_discord_task(coro)

@app.route('/api/<server_id>/moderation/logs/export', methods=['GET'], endpoint='export_moderation_logs')
def export_moderation_logs(server_id):
    """Export moderation logs as CSV/JSON"""
    if not data_manager_instance:
        return jsonify({'error': 'Data manager not available'}), 500

    try:
        guild_id = int(server_id)

        # Parse query parameters for filtering
        format_type = request.args.get('format', 'json')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        action_type = request.args.get('action')
        moderator_id = request.args.get('moderator_id')
        target_user_id = request.args.get('target_user_id')
        limit = min(int(request.args.get('limit', 1000)), 10000)  # Max 10k for export

        # Parse dates
        start_date = None
        end_date = None
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'error': 'Invalid start_date format'}), 400
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'error': 'Invalid end_date format'}), 400

        # Load moderation data
        moderation_data = data_manager_instance.load_guild_data(guild_id, 'moderation')
        if not moderation_data:
            return jsonify({'error': 'No moderation data found'}), 404

        logs = moderation_data.get('logs', [])

        # Apply filters
        filtered_logs = []
        for log_entry in logs:
            # Date filtering
            if start_date or end_date:
                try:
                    log_date = datetime.fromisoformat(log_entry.get('timestamp', ''))
                    if start_date and log_date < start_date:
                        continue
                    if end_date and log_date > end_date:
                        continue
                except (ValueError, TypeError):
                    continue  # Skip invalid dates

            # Action type filtering
            if action_type and log_entry.get('action') != action_type:
                continue

            # Moderator filtering
            if moderator_id and str(log_entry.get('moderator_id', '')) != str(moderator_id):
                continue

            # Target user filtering
            if target_user_id and str(log_entry.get('target_user_id', '')) != str(target_user_id):
                continue

            filtered_logs.append(log_entry)

        # Sort by timestamp descending
        filtered_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Apply limit
        filtered_logs = filtered_logs[:limit]

        if format_type == 'csv':
            # Create CSV response
            import io
            import csv

            output = io.StringIO()
            fieldnames = [
                'timestamp', 'action', 'moderator_id', 'moderator_name',
                'target_user_id', 'target_username', 'reason', 'duration',
                'channel_id', 'message_id', 'details'
            ]

            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()

            for log_entry in filtered_logs:
                writer.writerow({
                    'timestamp': log_entry.get('timestamp', ''),
                    'action': log_entry.get('action', ''),
                    'moderator_id': log_entry.get('moderator_id', ''),
                    'moderator_name': log_entry.get('moderator_name', ''),
                    'target_user_id': log_entry.get('target_user_id', ''),
                    'target_username': log_entry.get('target_username', ''),
                    'reason': log_entry.get('reason', ''),
                    'duration': log_entry.get('duration', ''),
                    'channel_id': log_entry.get('channel_id', ''),
                    'message_id': log_entry.get('message_id', ''),
                    'details': json.dumps(log_entry.get('details', {}))
                })

            output.seek(0)

            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename=moderation_logs_{server_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                }
            )

        else:  # JSON format
            return Response(
                json.dumps({
                    'server_id': server_id,
                    'exported_at': datetime.now().isoformat(),
                    'total_logs': len(filtered_logs),
                    'filters': {
                        'start_date': start_date_str,
                        'end_date': end_date_str,
                        'action_type': action_type,
                        'moderator_id': moderator_id,
                        'target_user_id': target_user_id,
                        'limit': limit
                    },
                    'logs': filtered_logs
                }, indent=2),
                mimetype='application/json',
                headers={
                    'Content-Disposition': f'attachment; filename=moderation_logs_{server_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
                }
            )

    except Exception as e:
        logger.error(f"Error exporting moderation logs: {e}")
        return jsonify({'error': str(e)}), 500

# === GLOBAL ERROR HANDLERS ===

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found', 'path': request.path}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"500 Error: {error}", exc_info=True)
    return jsonify({'error': 'Internal server error', 'message': str(error)}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """Handle all other exceptions"""
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    return jsonify({'error': 'Server error', 'message': str(e)}), 500

if __name__ == '__main__':
    run_backend()
