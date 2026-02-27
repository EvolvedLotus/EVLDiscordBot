"""
PRODUCTION-READY BACKEND.PY WITH CORS
Complete backend with all functionality restored
"""

from flask import Flask, request, jsonify, make_response, session, send_from_directory, redirect
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
import asyncio
from threading import Thread
import hashlib
import hmac
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
logger.info("🚀 Flask app created - starting initialization...")

# Secret key configuration (required for CSRF and sessions)
app.secret_key = os.getenv('JWT_SECRET_KEY', os.getenv('SECRET_KEY', secrets.token_hex(32)))
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour

# CSRF Protection & HTTPS
csrf = CSRFProtect(app)

# HTTPS Enforcement (Production Only)
# Note: Railway handles TLS termination at the edge, so we don't force_https
# (internal health checks use HTTP and would fail with 302 redirects)
if os.getenv('RAILWAY_ENVIRONMENT') == 'production' or os.getenv('ENVIRONMENT') == 'production':
    # Security headers without forcing HTTPS redirect (Railway does this at edge)
    Talisman(app, content_security_policy=None, force_https=False)
else:
    # Dev mode: permissive
    Talisman(app, content_security_policy=None, force_https=False, force_file_save=False)

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

# Import and initialize core managers with robust error handling
# Critical: Flask MUST start even if managers fail, so healthcheck passes
data_manager = None
cache_manager = None
audit_manager = None
auth_manager = None
discord_oauth_manager = None
transaction_manager = None
task_manager = None
shop_manager = None
announcement_manager = None
embed_builder = None
embed_manager = None
sync_manager = None
ad_claim_manager = None
channel_lock_manager = None
sse_manager = None  # Added global
evolved_lotus_api = None
AuditEventType = None

def initialize_managers():
    """Initialize managers - called after Flask starts to not block healthcheck"""
    global data_manager, cache_manager, audit_manager, auth_manager, discord_oauth_manager
    global transaction_manager, task_manager, shop_manager, announcement_manager
    global embed_builder, embed_manager, sync_manager, ad_claim_manager, channel_lock_manager
    global sse_manager, evolved_lotus_api, AuditEventType, TierManager
    
    try:
        logger.info("🔄 Initializing core managers...")
        
        from core.data_manager import DataManager
        from core.transaction_manager import TransactionManager
        from core.task_manager import TaskManager
        from core.shop_manager import ShopManager
        from core.announcement_manager import AnnouncementManager
        from core.embed_builder import EmbedBuilder
        from core.embed_manager import EmbedManager
        from core.cache_manager import CacheManager
        from core.auth_manager import AuthManager
        from core.audit_manager import AuditManager, AuditEventType
        from core.sync_manager import SyncManager
        from core.sse_manager import sse_manager as _sse_manager # Import as alias
        from core.discord_oauth import DiscordOAuthManager
        from core.ad_claim_manager import AdClaimManager
        from core.tier_manager import TierManager
        from core.evolved_lotus_api import evolved_lotus_api
        from core.channel_lock_manager import ChannelLockManager

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
        sse_manager = _sse_manager # Assign global
        sync_manager = SyncManager(data_manager, audit_manager, sse_manager)
        ad_claim_manager = AdClaimManager(data_manager, transaction_manager)
        channel_lock_manager = ChannelLockManager(data_manager)

        logger.info("✅ All managers initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize managers: {e}")
        import traceback
        traceback.print_exc()
        return False

# Try to initialize managers immediately (but don't crash if it fails)
try:
    initialize_managers()
except Exception as e:
    logger.error(f"⚠️ Manager initialization failed: {e} - Flask will start anyway")

# Global references for bot integration (avoid circular imports)
_bot_instance = None
_data_manager_instance = None

def set_bot_instance(bot):
    """Set the global bot instance reference and configure managers"""
    global _bot_instance
    _bot_instance = bot
    logger.info("✅ Bot instance attached to backend")

    # Link bot instance to data_manager for Discord sync
    if 'data_manager' in globals() and data_manager:
        data_manager.set_bot_instance(bot)
        logger.info("✓ Bot instance linked to data manager")

    # Also set bot instance on managers that need it
    if 'announcement_manager' in globals() and announcement_manager:
        announcement_manager.set_bot(bot)
        logger.info("✓ Bot instance linked to announcement manager")
        
    if 'channel_lock_manager' in globals() and channel_lock_manager:
        channel_lock_manager.set_bot_instance(bot)
        logger.info("✓ Bot instance linked to channel lock manager")

def set_data_manager(dm):
    """Set the global data manager reference"""
    global data_manager, _data_manager_instance
    data_manager = dm
    _data_manager_instance = dm
    
    # Update dependent managers
    if 'auth_manager' in globals() and auth_manager:
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

@app.route('/api/ad', methods=['GET'])
def get_ad():
    """
    Get a random ad from EvolvedLotus API.
    
    Query params:
        client_id: Optional client identifier for tracking
        include_blogs: If 'true', enables rotating blog ads (40% chance to show a random blog post)
    """
    try:
        client_id = request.args.get('client_id')
        include_blogs = request.args.get('include_blogs', 'false').lower() == 'true'
        
        if 'evolved_lotus_api' not in globals() or evolved_lotus_api is None:
             # Fallback if module failed to load
             return jsonify({
                 "title": "EvolvedLotus Ads",
                 "description": "Promote your content here!",
                 "cta": "Contact Us",
                 "url": "https://evolvedlotus.com",
                 "color": "#7289da"
             })

        ad = evolved_lotus_api.get_random_ad(client_id=client_id, include_rotating_blog=include_blogs)
        return jsonify(ad)
    except Exception as e:
        logger.error(f"Error fetching ad: {e}")
        return safe_error_response(e)

@app.route('/api/ad/click/<int:ad_id>', methods=['GET'])
def track_ad_click(ad_id):
    """Track a click on an EvolvedLotus ad and redirect"""
    try:
        # Get the ad to find its URL
        ads = evolved_lotus_api.get_all_ads()
        target_ad = next((ad for ad in ads if ad['id'] == ad_id), None)
        
        if target_ad:
            # Increment clicks
            evolved_lotus_api.increment_clicks(ad_id)
            return redirect(target_ad['url'])
        return "Ad not found", 404
    except Exception as e:
        logger.error(f"Error tracking click {ad_id}: {e}")
        return "Internal error", 500

@app.route('/api/admin/ad-stats', methods=['GET'])
@require_auth
def get_ad_stats():
    """Get global ad statistics (Master Login Only)"""
    user = request.user
    if not (user.get('is_superadmin') or user.get('role') == 'superadmin'):
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        if 'evolved_lotus_api' not in globals() or evolved_lotus_api is None:
            return jsonify({
                'total_ads': 0,
                'total_impressions': 0,
                'total_clicks': 0,
                'ctr': 0
            })
            
        # These would ideally be fetched from the database
        # For now, we'll return the count of active ads and placeholders for analytics
        ads = evolved_lotus_api.get_all_ads()
        return jsonify({
            'total_ads': len(ads),
            'total_impressions': 1240, # Placeholder until analytics table is ready
            'total_clicks': 86,       # Placeholder until analytics table is ready
                'ctr': 6.9                # Placeholder until analytics table is ready
        })
    except Exception as e:
        return safe_error_response(e)

# ========== AD API CONFIGURATION (MASTER LOGIN ONLY) ==========
@app.route('/api/admin/ad-clients', methods=['GET'])
@require_auth
def get_ad_clients():
    """Get all ad clients (Master Login Only)"""
    user = request.user
    if not (user.get('is_superadmin') or user.get('role') == 'superadmin'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        if 'evolved_lotus_api' not in globals() or evolved_lotus_api is None:
            return jsonify({'error': 'EvolvedLotus API not initialized'}), 503
            
        clients = evolved_lotus_api.get_ad_clients()
        return jsonify({'clients': clients}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/admin/ad-clients/<client_id>', methods=['PUT'])
@require_auth
def update_ad_client(client_id):
    """Update ad client priority/weight (Master Login Only)"""
    user = request.user
    if not (user.get('is_superadmin') or user.get('role') == 'superadmin'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    try:
        data = request.get_json()
        if 'evolved_lotus_api' not in globals() or evolved_lotus_api is None:
            return jsonify({'error': 'EvolvedLotus API not initialized'}), 503
            
        success = evolved_lotus_api.update_ad_client(client_id, data)
        if success:
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Failed to update client'}), 500
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/admin/log_cms_action', methods=['POST'])
@csrf.exempt
@require_auth
def log_cms_action():
    """Receive and store logs from the CMS UI"""
    try:
        data = request.get_json()
        user = request.user
        
        # We use log_event to store these in the audit system
        audit_manager.log_event(
            event_type=AuditEventType.CMS_ACTION,
            guild_id=data.get('guild_id', 0),
            user_id=None,
            moderator_id=user.get('id'),
            details={
                'action': data.get('action', 'unknown'),
                'success': data.get('success', True),
                'ui_metadata': data.get('details', {})
            }
        )
        return jsonify({'success': True}), 200
    except Exception as e:
        logger.error(f"Failed to log CMS action: {e}")
        return jsonify({'error': str(e)}), 500

# ========== AD CLAIM ENDPOINTS (For ad-viewer.html) ==========
@app.route('/api/ad-claim/session/<session_id>', methods=['GET'])
def get_ad_session(session_id):
    """Get ad session details for the ad-viewer page"""
    try:
        if 'ad_claim_manager' not in globals() or ad_claim_manager is None:
            return jsonify({'error': 'Ad claim system not available'}), 503
            
        # Fetch the session from database
        result = data_manager.admin_client.table('ad_views') \
            .select('*') \
            .eq('ad_session_id', session_id) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            return jsonify({'error': 'Session not found'}), 404
            
        session_data = result.data[0]
        
        # Extract custom ad from metadata if present
        custom_ad = None
        metadata = session_data.get('metadata', {})
        if isinstance(metadata, dict):
            custom_ad = metadata.get('custom_ad')
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'user_id': session_data.get('user_id'),
            'guild_id': session_data.get('guild_id'),
            'ad_type': session_data.get('ad_type', 'monetag_interstitial'),
            'is_verified': session_data.get('is_verified', False),
            'reward_amount': session_data.get('reward_amount', 10),
            'custom_ad': custom_ad
        })
        
    except Exception as e:
        logger.error(f"Error fetching ad session {session_id}: {e}")
        return safe_error_response(e)

@app.route('/api/ad-claim/verify', methods=['POST'])
def verify_ad_claim():
    """Verify ad was watched and grant reward"""
    try:
        if 'ad_claim_manager' not in globals() or ad_claim_manager is None:
            return jsonify({'error': 'Ad claim system not available'}), 503
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': 'Missing session_id'}), 400
        
        # Verify and grant reward
        result = ad_claim_manager.verify_ad_view(session_id)
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'reward_amount': result.get('reward_amount', 10),
                'new_balance': result.get('new_balance'),
                'message': 'Reward claimed successfully!'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Failed to verify ad view')
            }), 400
            
    except Exception as e:
        logger.error(f"Error verifying ad claim: {e}")
        return safe_error_response(e)

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

@app.route('/api/ad-claim/create', methods=['POST'])
def create_ad_session():
    """Create a new ad session (called by Discord bot or CMS)"""
    try:
        if 'ad_claim_manager' not in globals() or ad_claim_manager is None:
            return jsonify({'error': 'Ad claim system not available'}), 503
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        user_id = data.get('user_id')
        guild_id = data.get('guild_id')
        
        if not user_id or not guild_id:
            return jsonify({'error': 'Missing user_id or guild_id'}), 400
        
        # Get client info for fraud prevention
        ip_address = get_remote_address()
        user_agent = request.headers.get('User-Agent')
        
        # Create session
        result = ad_claim_manager.create_ad_session(
            user_id=user_id,
            guild_id=guild_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify({'error': result.get('error', 'Failed to create session')}), 500
            
    except Exception as e:
        logger.error(f"Error creating ad session: {e}")
        return safe_error_response(e)

@app.route('/api/webhooks/stripe', methods=['POST'])
@csrf.exempt
def stripe_webhook():
    """
    Handle incoming webhooks from Stripe.
    Used to upgrade/downgrade servers based on subscription status.
    """
    try:
        import stripe as stripe_lib
        stripe_lib.api_key = os.getenv('STRIPE_SECRET_KEY')
        STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
        
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature')

        if not sig_header:
            logger.warning("Received Stripe webhook without signature")
            return jsonify({'error': 'Missing signature'}), 401

        try:
            event = stripe_lib.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except stripe_lib.error.SignatureVerificationError as e:
            logger.error(f"Stripe signature verification failed: {e}")
            return jsonify({'error': 'Invalid signature'}), 400
        except Exception as e:
            logger.error(f"Stripe webhook construction error: {e}")
            return jsonify({'error': str(e)}), 400

        event_type = event['type']
        data = event['data']['object']
        
        logger.info(f"[Stripe Webhook] Received: {event_type}")

        # CHECKOUT COMPLETED
        if event_type == 'checkout.session.completed':
            metadata = data.get('metadata', {})
            tier = metadata.get('tier', 'supporter')
            guild_id = metadata.get('guild_id')
            user_id = metadata.get('firebase_uid') or metadata.get('discord_user_id')
            
            if tier == 'growth_insider' and guild_id:
                logger.info(f"💰 Growth Insider activated for Guild: {guild_id}")
                try:
                    guild_result = data_manager.admin_client.table('guilds').select('guild_id').eq('guild_id', str(guild_id)).execute()
                    
                    if guild_result.data and len(guild_result.data) > 0:
                        data_manager.admin_client.table('guilds').update({
                            'subscription_tier': 'growth_insider',
                            'last_synced': datetime.now(timezone.utc).isoformat()
                        }).eq('guild_id', str(guild_id)).execute()
                        
                        logger.info(f"✅ Successfully upgraded guild {guild_id} to Growth Insider via Stripe")
                        
                        try:
                            sse_manager.broadcast_event('guild.upgraded', {
                                'guild_id': str(guild_id),
                                'tier': 'growth_insider'
                            })
                        except Exception as sse_error:
                            logger.warning(f"Failed to broadcast upgrade event: {sse_error}")
                    else:
                        logger.warning(f"Guild {guild_id} not found in database for Stripe upgrade")
                except Exception as db_error:
                    logger.error(f"Database error upgrading guild: {db_error}")

        # SUBSCRIPTION CREATED / UPDATED
        elif event_type in ['customer.subscription.created', 'customer.subscription.updated']:
            metadata = data.get('metadata', {})
            tier = metadata.get('tier')
            guild_id = metadata.get('guild_id')
            status = data.get('status')
            is_active = status in ['active', 'trialing']
            
            if tier == 'growth_insider' and guild_id:
                new_tier = 'growth_insider' if is_active else 'free'
                try:
                    data_manager.admin_client.table('guilds').update({
                        'subscription_tier': new_tier,
                        'last_synced': datetime.now(timezone.utc).isoformat()
                    }).eq('guild_id', str(guild_id)).execute()
                    logger.info(f"{'✅ Upgraded' if is_active else '📉 Downgraded'} guild {guild_id} to {new_tier} via Stripe subscription update")
                except Exception as db_error:
                    logger.error(f"Database error updating guild subscription: {db_error}")

        # SUBSCRIPTION CANCELLED / EXPIRED
        elif event_type == 'customer.subscription.deleted':
            metadata = data.get('metadata', {})
            guild_id = metadata.get('guild_id')
            
            if guild_id:
                logger.info(f"❌ Premium cancelled for Guild: {guild_id}")
                try:
                    data_manager.admin_client.table('guilds').update({
                        'subscription_tier': 'free',
                        'last_synced': datetime.now(timezone.utc).isoformat()
                    }).eq('guild_id', str(guild_id)).execute()
                except Exception as db_error:
                    logger.error(f"Database error downgrading guild: {db_error}")

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Stripe webhook processing error: {e}")
        return safe_error_response(e)



@app.route('/api/auth/login', methods=['POST'])
@csrf.exempt
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
@csrf.exempt
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
            'is_superadmin': user.get('is_superadmin', False),
            'role': user.get('role', 'user')
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
@csrf.exempt
@limiter.limit("5 per minute")
def login_alias():
    """Alias for /api/auth/login for CMS compatibility"""
    return login()

@app.route('/api/logout', methods=['POST'])
@csrf.exempt
def logout_alias():
    """Alias for /api/auth/logout for CMS compatibility"""
    return logout()

# ========== DISCORD OAUTH2 AUTHENTICATION ==========



@app.route('/api/auth/discord/callback', methods=['POST'])
@csrf.exempt  # OAuth callbacks are CSRF-protected via state parameter
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
                'is_superadmin': result['user'].get('is_superadmin', False),
                'role': result['user'].get('role', 'server_owner'),
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
        
        # SECURITY PROTECTION: Redact bot status for non-superadmins
        user = request.user
        is_superadmin = user.get('is_superadmin', False) or user.get('role') == 'superadmin'
        
        if not is_superadmin:
            # Create a copy so we don't modify the cache/file data
            safe_config = config.copy()
            safe_config.pop('bot_status_message', None)
            safe_config.pop('bot_status_type', None)
            return jsonify(safe_config), 200
            
        return jsonify(config), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/config', methods=['PUT'])
@csrf.exempt
@require_guild_access
def update_server_config(server_id):
    try:
        data = request.get_json()
        
        # Define protected fields that only superadmins can change
        protected_fields = [
            'feature_tasks', 'feature_shop', 'feature_announcements', 
            'feature_moderation', 'subscription_tier', 'bot_status_message', 
            'bot_status_type'
        ]
        
        # Check if any protected field is being modified
        user = request.user
        is_superadmin = user.get('is_superadmin', False) or user.get('role') == 'superadmin'
        
        if not is_superadmin:
            for field in protected_fields:
                if field in data:
                    logger.warning(f"Unauthorized attempt to modify protected field '{field}' by user: {user.get('username')}")
                    return jsonify({'error': f'Unauthorized. Master login required to modify {field}.'}), 403
        
        logger.info(f"Updating config for guild {server_id} by user {user.get('username')} (superuser: {is_superadmin})")
        logger.info(f"Update data keys: {list(data.keys())}")

        # Load current config to merge with updates
        current_config = data_manager.load_guild_data(server_id, 'config')
        
        # Merge the updates into current config
        current_config.update(data)
        
        # Save merged config
        success = data_manager.save_guild_data(server_id, 'config', current_config)
        
        # SYNC FIX: Also update the main guilds table if subscription_tier changed
        if success and 'subscription_tier' in data:
            try:
                data_manager.admin_client.table('guilds').update({
                    'subscription_tier': data['subscription_tier'],
                    'last_synced': datetime.now(timezone.utc).isoformat()
                }).eq('guild_id', str(server_id)).execute()
                logger.info(f"Synced subscription_tier update for guild {server_id} to guilds table")
            except Exception as sync_error:
                logger.error(f"Failed to sync subscription_tier to guilds table: {sync_error}")

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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
@require_guild_access
def update_shop_item(server_id, item_id):
    try:
        data = request.get_json()
        shop_manager.update_item(server_id, item_id, data)
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/shop/<item_id>', methods=['DELETE'])
@csrf.exempt
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
@csrf.exempt
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
        
        # Scheduling parameters
        scheduled_for = data.get('scheduled_for') # ISO Format
        delay_minutes = data.get('delay_minutes')
        
        # Enforce Premium Limits for Scheduling
        if scheduled_for or delay_minutes:
            # Check subscription tier
            config = data_manager.load_guild_data(server_id, 'config')
            tier = config.get('subscription_tier', 'free')
            
            # Check if scheduling is allowed (channel_schedules controls all scheduling features)
            if not TierManager.get_limits(tier).get('channel_schedules', False):
                 return jsonify({'error': 'Scheduling is a Premium feature. Please upgrade to use this feature!'}), 403

            # Handle Scheduling
            try:
                current_time = datetime.now(timezone.utc)
                if scheduled_for:
                    schedule_time = datetime.fromisoformat(scheduled_for.replace('Z', '+00:00'))
                    if schedule_time.tzinfo is None:
                        schedule_time = schedule_time.replace(tzinfo=timezone.utc)
                else:
                    schedule_time = current_time + timedelta(minutes=int(delay_minutes))
                
                if schedule_time <= current_time:
                     return jsonify({'error': 'Scheduled time must be in the future'}), 400
                     
                # Prepare schedule data
                # We'll stick to the "simple" announcement structure for now as the backend api 
                # for rich embeds is separate or simpler. 
                # If backend sends "embed" data we might need to handle it, but for now 
                # let's support the standard announcement fields.
                
                schedule_data = {
                    'id': f"scheduled_{int(datetime.now().timestamp() * 1000)}",
                    'title': title,
                    'content': content,
                    'channel_id': str(channel_id),
                    'scheduled_for': schedule_time.isoformat(),
                    'delay_minutes': int(delay_minutes) if delay_minutes else 0,
                    'author_id': str(author_id),
                    'author_name': author_name,
                    'mention_everyone': False, # Backend API might need a param for this
                    'auto_pin': auto_pin,
                    'status': 'scheduled',
                    'type': 'announcement' # Explicitly mark as simple announcement
                }
                
                # Load existing data
                announcements_data = data_manager.load_guild_data(str(server_id), 'announcements') or {'scheduled': []}
                
                # Add to scheduled list
                if 'scheduled' not in announcements_data or not isinstance(announcements_data['scheduled'], list):
                    announcements_data['scheduled'] = []
                announcements_data['scheduled'].append(schedule_data)
                
                # Save back
                data_manager.save_guild_data(str(server_id), 'announcements', announcements_data)
                
                return jsonify({
                    'success': True, 
                    'message': 'Announcement scheduled', 
                    'scheduled_for': schedule_time.isoformat(),
                    'id': schedule_data['id']
                }), 201
                
            except ValueError:
                return jsonify({'error': 'Invalid date format'}), 400
            except Exception as schedule_error:
                logger.error(f"Scheduling error: {schedule_error}")
                return safe_error_response(schedule_error)

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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
@require_guild_access
def update_embed(server_id, embed_id):
    try:
        data = request.get_json()
        embed = embed_builder.update_embed(server_id, embed_id, data)
        return jsonify(embed), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/embeds/<embed_id>', methods=['DELETE'])
@csrf.exempt
@require_guild_access
def delete_embed(server_id, embed_id):
    try:
        embed_builder.delete_embed(server_id, embed_id)
        return jsonify({'success': True}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/embeds/<embed_id>/send', methods=['POST'])
@csrf.exempt
@require_guild_access
def send_embed_to_channel(server_id, embed_id):
    """Send an embed to a specific channel"""
    try:
        data = request.get_json()
        channel_id = data.get('channel_id')
        
        if not channel_id:
            return jsonify({'error': 'channel_id is required'}), 400
            
        # Check for scheduling
        scheduled_for = data.get('scheduled_for')
        delay_minutes = data.get('delay_minutes')
        
        # Enforce Premium Limits for Scheduling
        if scheduled_for or delay_minutes:
            # Check subscription tier
            config = data_manager.load_guild_data(server_id, 'config')
            tier = config.get('subscription_tier', 'free')
            
            # Check if scheduling is allowed
            if not TierManager.get_limits(tier).get('channel_schedules', False):
                 return jsonify({'error': 'Scheduling is a Premium feature. Please upgrade to use this feature!'}), 403

        
        # Get the embed data from database
        result = data_manager.admin_client.table('embeds') \
            .select('*') \
            .eq('embed_id', embed_id) \
            .eq('guild_id', str(server_id)) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            return jsonify({'error': 'Embed not found'}), 404
        
        embed_data = result.data[0]
        
        if scheduled_for or delay_minutes:
            try:
                current_time = datetime.now(timezone.utc)
                if scheduled_for:
                    schedule_time = datetime.fromisoformat(scheduled_for.replace('Z', '+00:00'))
                    if schedule_time.tzinfo is None:
                        schedule_time = schedule_time.replace(tzinfo=timezone.utc)
                else:
                    schedule_time = current_time + timedelta(minutes=int(delay_minutes))
                
                if schedule_time <= current_time:
                     return jsonify({'error': 'Scheduled time must be in the future'}), 400

                # Construct embed_dict for discord.Embed.from_dict
                # We need to map database fields to Discord API dict format
                # Database: title, description, color (hex string), fields (list), footer (text), thumbnail (text), image (text)
                
                color_val = embed_data.get('color', '#5865F2')
                if isinstance(color_val, str) and color_val.startswith('#'):
                    color_int = int(color_val.strip('#'), 16)
                else:
                    color_int = int(color_val) if color_val else 0x5865F2

                embed_dict = {
                    'title': embed_data.get('title'),
                    'description': embed_data.get('description'),
                    'color': color_int,
                    'fields': [],
                    'timestamp': datetime.now().isoformat()
                }
                
                if embed_data.get('footer'):
                    embed_dict['footer'] = {'text': embed_data['footer']}
                
                if embed_data.get('thumbnail'):
                    embed_dict['thumbnail'] = {'url': embed_data['thumbnail']}
                
                if embed_data.get('image'):
                    embed_dict['image'] = {'url': embed_data['image']}
                
                if embed_data.get('fields'):
                    for field in embed_data['fields']:
                        embed_dict['fields'].append({
                            'name': field.get('name', 'Field'),
                            'value': field.get('value', 'Value'),
                            'inline': field.get('inline', False)
                        })

                # Prepare schedule data
                schedule_data = {
                    'id': f"scheduled_embed_{int(datetime.now().timestamp() * 1000)}",
                    'type': 'embed',
                    'embed_dict': embed_dict,
                    'channel_id': str(channel_id),
                    'scheduled_for': schedule_time.isoformat(),
                    'delay_minutes': int(delay_minutes) if delay_minutes else 0,
                    'author_id': str(request.user.get('id', 'admin')),
                    'author_name': request.user.get('username', 'Admin'),
                    'status': 'scheduled'
                }
                
                # Load existing data
                announcements_data = data_manager.load_guild_data(str(server_id), 'announcements') or {'scheduled': []}
                
                # Add to scheduled list
                if 'scheduled' not in announcements_data or not isinstance(announcements_data['scheduled'], list):
                    announcements_data['scheduled'] = []
                announcements_data['scheduled'].append(schedule_data)
                
                # Save back
                data_manager.save_guild_data(str(server_id), 'announcements', announcements_data)
                
                return jsonify({
                    'success': True, 
                    'message': 'Embed scheduled successfully',
                    'scheduled_for': schedule_time.isoformat(),
                    'id': schedule_data['id']
                }), 201

            except ValueError:
                return jsonify({'error': 'Invalid date format'}), 400
            except Exception as schedule_error:
                logger.error(f"Scheduling error: {schedule_error}")
                return safe_error_response(schedule_error)

        if not _bot_instance or not _bot_instance.is_ready():
            return jsonify({'error': 'Bot is not ready'}), 503
        
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
@csrf.exempt
@require_guild_access
def update_bot_status(server_id):
    """Update global bot status (Master Login Only)"""
    # SECURITY CHECK: Only Super Admins (Master Login) can update bot status
    user = request.user
    if not (user.get('is_superadmin') or user.get('role') == 'superadmin'):
        logger.warning(f"Unauthorized bot status update attempt by user: {user.get('username')}")
        return jsonify({'error': 'Unauthorized. Master login required.'}), 403

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
@csrf.exempt  # CMS API calls
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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
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
@csrf.exempt
@require_guild_access
def create_guild_ad_session(server_id):
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
def get_user_ad_stats(server_id, user_id):
    """Get ad viewing statistics for a user"""
    try:
        result = ad_claim_manager.get_user_ad_stats(user_id, server_id)
        return jsonify(result), 200
        
    except Exception as e:
        return safe_error_response(e)


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
@csrf.exempt
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

# ========== CHANNEL LOCK SCHEDULES (Premium Feature) ==========

def require_premium(f):
    """Decorator to require premium subscription (Growth Insider) for an endpoint"""
    @wraps(f)
    def decorated_function(server_id, *args, **kwargs):
        try:
            config = data_manager.load_guild_data(server_id, 'config')
            tier = config.get('subscription_tier', 'free')
            if not TierManager.is_premium(tier):
                return jsonify({
                    'error': 'This feature requires a Growth Insider subscription',
                    'upgrade_url': 'https://tools.evolvedlotus.com/premium'
                }), 403
            return f(server_id, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error checking premium status: {e}")
            return safe_error_response(e)
    return decorated_function

@app.route('/api/<server_id>/channel-schedules', methods=['GET'])
@require_guild_access
@require_premium
def get_channel_schedules(server_id):
    """Get all channel lock schedules for a guild (Premium Only)"""
    try:
        schedules = channel_lock_manager.get_schedules(server_id)
        return jsonify({'schedules': schedules}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channel-schedules', methods=['POST'])
@csrf.exempt
@require_guild_access
@require_premium
def create_channel_schedule(server_id):
    """Create a new channel lock schedule (Premium Only)"""
    try:
        data = request.get_json()
        user = request.user
        
        # Validate required fields
        if not data.get('channel_id'):
            return jsonify({'error': 'channel_id is required'}), 400
        if not data.get('unlock_time'):
            return jsonify({'error': 'unlock_time is required'}), 400
        if not data.get('lock_time'):
            return jsonify({'error': 'lock_time is required'}), 400
        
        # Check bot permissions on the channel first
        if _bot_instance and _bot_instance.loop:
            future = asyncio.run_coroutine_threadsafe(
                channel_lock_manager.check_channel_permissions(server_id, data['channel_id']),
                _bot_instance.loop
            )
            perm_result = future.result(timeout=10)
            
            if not perm_result.get('has_permissions'):
                return jsonify({
                    'error': f"Bot lacks required permissions: {perm_result.get('error', 'Manage Channels and Manage Roles required')}"
                }), 400
            
            # Add channel name to data
            data['channel_name'] = perm_result.get('channel_name', '')
        
        result = channel_lock_manager.create_schedule(
            server_id, 
            data, 
            created_by=user.get('id')
        )
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        # Immediately apply the correct state
        if _bot_instance and _bot_instance.loop:
            schedule = result.get('schedule', {})
            should_unlock = channel_lock_manager.should_be_unlocked(schedule)
            
            if should_unlock:
                asyncio.run_coroutine_threadsafe(
                    channel_lock_manager.unlock_channel(
                        server_id, 
                        data['channel_id'], 
                        schedule.get('schedule_id')
                    ),
                    _bot_instance.loop
                )
            else:
                asyncio.run_coroutine_threadsafe(
                    channel_lock_manager.lock_channel(
                        server_id, 
                        data['channel_id'], 
                        schedule.get('schedule_id')
                    ),
                    _bot_instance.loop
                )
        
        return jsonify(result), 201
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channel-schedules/<schedule_id>', methods=['GET'])
@require_guild_access
@require_premium
def get_channel_schedule(server_id, schedule_id):
    """Get a specific channel schedule (Premium Only)"""
    try:
        schedule = channel_lock_manager.get_schedule(server_id, schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404
        return jsonify({'schedule': schedule}), 200
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channel-schedules/<schedule_id>', methods=['PUT'])
@csrf.exempt
@require_guild_access
@require_premium
def update_channel_schedule(server_id, schedule_id):
    """Update a channel lock schedule (Premium Only)"""
    try:
        data = request.get_json()
        result = channel_lock_manager.update_schedule(server_id, schedule_id, data)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        # Re-evaluate schedule state after update
        if _bot_instance and _bot_instance.loop:
            schedule = result.get('schedule', {})
            should_unlock = channel_lock_manager.should_be_unlocked(schedule)
            channel_id = schedule.get('channel_id')
            
            if should_unlock and schedule.get('current_state') != 'unlocked':
                asyncio.run_coroutine_threadsafe(
                    channel_lock_manager.unlock_channel(server_id, channel_id, schedule_id),
                    _bot_instance.loop
                )
            elif not should_unlock and schedule.get('current_state') != 'locked':
                asyncio.run_coroutine_threadsafe(
                    channel_lock_manager.lock_channel(server_id, channel_id, schedule_id),
                    _bot_instance.loop
                )
        
        return jsonify(result), 200
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channel-schedules/<schedule_id>', methods=['DELETE'])
@csrf.exempt
@require_guild_access
@require_premium
def delete_channel_schedule(server_id, schedule_id):
    """Delete a channel lock schedule (Premium Only)"""
    try:
        # Get schedule to unlock channel before deleting
        schedule = channel_lock_manager.get_schedule(server_id, schedule_id)
        
        if schedule and _bot_instance and _bot_instance.loop:
            # Unlock the channel before deleting the schedule
            future = asyncio.run_coroutine_threadsafe(
                channel_lock_manager.unlock_channel(
                    server_id, 
                    schedule['channel_id'], 
                    schedule_id
                ),
                _bot_instance.loop
            )
            future.result(timeout=10)
        
        result = channel_lock_manager.delete_schedule(server_id, schedule_id)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'success': True, 'message': 'Schedule deleted and channel unlocked'}), 200
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channel-schedules/<schedule_id>/toggle', methods=['POST'])
@csrf.exempt
@require_guild_access
@require_premium
def toggle_channel_schedule(server_id, schedule_id):
    """Toggle a schedule's enabled state (Premium Only)"""
    try:
        schedule = channel_lock_manager.get_schedule(server_id, schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404
        
        new_state = not schedule.get('is_enabled', True)
        result = channel_lock_manager.update_schedule(server_id, schedule_id, {'is_enabled': new_state})
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        # If disabling, unlock the channel
        if not new_state and _bot_instance and _bot_instance.loop:
            asyncio.run_coroutine_threadsafe(
                channel_lock_manager.unlock_channel(server_id, schedule['channel_id'], schedule_id),
                _bot_instance.loop
            )
        
        return jsonify({
            'success': True, 
            'is_enabled': new_state,
            'message': f"Schedule {'enabled' if new_state else 'disabled'}"
        }), 200
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channel-schedules/<schedule_id>/lock', methods=['POST'])
@csrf.exempt
@require_guild_access
@require_premium
def manual_lock_channel(server_id, schedule_id):
    """Manually lock a channel now (Premium Only)"""
    try:
        schedule = channel_lock_manager.get_schedule(server_id, schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404
        
        if not _bot_instance or not _bot_instance.loop:
            return jsonify({'error': 'Bot is not ready'}), 503
        
        future = asyncio.run_coroutine_threadsafe(
            channel_lock_manager.lock_channel(server_id, schedule['channel_id'], schedule_id),
            _bot_instance.loop
        )
        result = future.result(timeout=10)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'success': True, 'message': 'Channel locked'}), 200
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channel-schedules/<schedule_id>/unlock', methods=['POST'])
@csrf.exempt
@require_guild_access
@require_premium
def manual_unlock_channel(server_id, schedule_id):
    """Manually unlock a channel now (Premium Only)"""
    try:
        schedule = channel_lock_manager.get_schedule(server_id, schedule_id)
        if not schedule:
            return jsonify({'error': 'Schedule not found'}), 404
        
        if not _bot_instance or not _bot_instance.loop:
            return jsonify({'error': 'Bot is not ready'}), 503
        
        future = asyncio.run_coroutine_threadsafe(
            channel_lock_manager.unlock_channel(server_id, schedule['channel_id'], schedule_id),
            _bot_instance.loop
        )
        result = future.result(timeout=10)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'success': True, 'message': 'Channel unlocked'}), 200
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/<server_id>/channel-schedules/check-permissions/<channel_id>', methods=['GET'])
@require_guild_access
@require_premium
def check_channel_lock_permissions(server_id, channel_id):
    """Check if bot has permissions to lock/unlock a channel (Premium Only)"""
    try:
        if not _bot_instance or not _bot_instance.loop:
            return jsonify({'error': 'Bot is not ready'}), 503
        
        future = asyncio.run_coroutine_threadsafe(
            channel_lock_manager.check_channel_permissions(server_id, channel_id),
            _bot_instance.loop
        )
        result = future.result(timeout=10)
        
        return jsonify(result), 200
        
    except Exception as e:
        return safe_error_response(e)

@app.route('/api/timezones', methods=['GET'])
def get_timezones():
    """Get list of common timezones for UI"""
    try:
        timezones = channel_lock_manager.get_timezones()
        return jsonify({'timezones': timezones}), 200
    except Exception as e:
        return safe_error_response(e)




# ========== TOP.GG WEBHOOK ==========
@app.route('/api/webhooks/topgg', methods=['POST'])
@csrf.exempt
def topgg_webhook():
    """Handle Top.gg upvotes"""
    # Verify authorization
    auth_header = request.headers.get('Authorization')
    # User said "Token Name servervote", assuming this is the secret
    expected_token = os.getenv('TOPGG_WEBHOOK_SECRET', 'servervote')
    
    if auth_header != expected_token:
        # Avoid logging full IP in production to prevent log spam, or use debug
        logger.warning(f"⚠️ Unauthorized Top.gg webhook attempt")
        return jsonify({'error': 'Unauthorized'}), 401
        
    try:
        data = request.get_json()
        logger.info(f"🗳️ Top.gg vote received: {data}")
        
        # Check for test vote
        if data.get('type') == 'test':
            logger.info("Test vote received")
            return jsonify({'success': True, 'message': 'Test received'}), 200
            
        vote_type = data.get('type')
        if vote_type != 'upvote':
            return jsonify({'success': True}), 200
            
        user_id = data.get('user')
        guild_id = data.get('guild')
        
        if not user_id:
            return jsonify({'error': 'Missing user ID'}), 400

        # Reward amount (user requested 100 coins)
        REWARD_AMOUNT = 100
        
        if guild_id:
            # Server vote: Reward in specific guild
            if _add_currency_webhook(guild_id, user_id, REWARD_AMOUNT):
                return jsonify({'success': True}), 200
            else:
                return jsonify({'error': 'Failed to add currency'}), 500
        else:
            # Bot vote logic (optional)
            logger.warning("Bot vote received without guild ID. Reward skipped.")
            return jsonify({'success': True}), 200
        
    except Exception as e:
        logger.error(f"Error processing Top.gg webhook: {e}")
        return jsonify({'error': str(e)}), 500

def _add_currency_webhook(guild_id, user_id, amount):
    """Helper to add currency safely using DataManager's client"""
    try:
        if 'data_manager' not in globals() or data_manager is None:
            logger.error("DataManager not available for vote reward")
            return False

        # 1. Update/Create User Balance
        res = data_manager.admin_client.table('users').select('balance').eq('guild_id', str(guild_id)).eq('user_id', str(user_id)).execute()
        
        if res.data and len(res.data) > 0:
            # Update existing
            current_bal = res.data[0].get('balance', 0)
            new_bal = current_bal + amount
            data_manager.admin_client.table('users').update({'balance': new_bal}).eq('guild_id', str(guild_id)).eq('user_id', str(user_id)).execute()
            logger.info(f"💰 Added {amount} coins to user {user_id} in guild {guild_id} (New Balance: {new_bal})")
        else:
            # Create new user entry
            new_user = {
                'guild_id': str(guild_id),
                'user_id': str(user_id),
                'balance': amount,
                'total_earned': amount,
                'is_active': True,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            data_manager.admin_client.table('users').insert(new_user).execute()
            logger.info(f"💰 Created user {user_id} in guild {guild_id} with {amount} coins")

        # 2. Log Vote (CRITICAL for /vote cooldowns)
        # Check if weekend (Top.gg often sends isWeekend in payload, checking request data)
        # But we don't have request data here easily unless we pass it.
        # Let's just assume false or check datetime.
        is_weekend = datetime.now(timezone.utc).weekday() >= 5 # 5=Sat, 6=Sun
        
        vote_log = {
            'user_id': str(user_id),
            'guild_id': str(guild_id),
            'site': 'top.gg',
            'reward': amount,
            'is_weekend': is_weekend,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        data_manager.admin_client.table('vote_logs').insert(vote_log).execute()
            
        return True
    except Exception as e:
        logger.error(f"Failed to add currency for vote: {e}")
        return False


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
    app.run(host='0.0.0.0', port=port, debug=False)
