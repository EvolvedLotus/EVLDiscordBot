"""
PRODUCTION-READY BACKEND.PY WITH CORS
Complete backend with all functionality restored
"""

from flask import Flask, request, jsonify, make_response, session, send_from_directory
from flask_cors import CORS
import os
import sys
import logging
from datetime import datetime, timedelta
import asyncio
from threading import Thread

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
    os.getenv('ENVIRONMENT') == 'production'
)

# CORS Configuration - Environment-based
def get_allowed_origins():
    """Get allowed CORS origins from environment variables"""
    # Check for ALLOWED_ORIGINS environment variable (comma-separated)
    allowed_origins_env = os.getenv('ALLOWED_ORIGINS', '').strip()

    if allowed_origins_env:
        # Parse comma-separated origins
        origins = [origin.strip() for origin in allowed_origins_env.split(',') if origin.strip()]
        if origins:
            logger.info(f"✅ CORS origins from ALLOWED_ORIGINS: {origins}")
            return origins

    # Check for ALLOWED_FRONTEND_DOMAINS (legacy support)
    frontend_domains = os.getenv('ALLOWED_FRONTEND_DOMAINS', '').strip()
    if frontend_domains:
        origins = [domain.strip() for domain in frontend_domains.split(',') if domain.strip()]
        if origins:
            logger.info(f"✅ CORS origins from ALLOWED_FRONTEND_DOMAINS: {origins}")
            return origins

    # Fallback to hardcoded defaults based on environment
    if IS_PRODUCTION:
        # Production defaults
        default_origins = [
            'https://evolvedlotus.github.io',
            'https://evolvedlotus.github.io/EVLDiscordBot',
        ]

        # Try to add Railway domain if available
        railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
        if railway_domain:
            railway_url = f'https://{railway_domain}'
            if railway_url not in default_origins:
                default_origins.append(railway_url)
                logger.info(f"✅ Added Railway domain to CORS: {railway_url}")

        logger.info(f"✅ Using production CORS defaults: {default_origins}")
        return default_origins
    else:
        # Development defaults
        default_origins = [
            'http://localhost:3000',
            'http://localhost:5000',
            'http://localhost:8000',
            'http://127.0.0.1:3000',
            'http://127.0.0.1:5000',
            'http://127.0.0.1:8000',
            'https://evolvedlotus.github.io',
        ]
        logger.info(f"✅ Using development CORS defaults: {default_origins}")
        return default_origins

ALLOWED_ORIGINS = get_allowed_origins()

CORS(app,
     origins=ALLOWED_ORIGINS,
     supports_credentials=True,
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'],
     expose_headers=['Content-Type', 'X-Total-Count'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
     max_age=3600
)

# Session configuration
app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-change-me')
app.config['SESSION_TYPE'] = 'filesystem'

if IS_PRODUCTION:
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_DOMAIN'] = '.railway.app'
else:
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_DOMAIN'] = None

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_PATH'] = '/'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400

# Import core managers
try:
    from core.data_manager import DataManager
    from core.transaction_manager import TransactionManager
    from core.task_manager import TaskManager
    from core.shop_manager import ShopManager
    from core.announcement_manager import AnnouncementManager
    from core.embed_builder import EmbedBuilder
    from core.cache_manager import CacheManager
    from core.auth_manager import AuthManager
    from core.audit_manager import AuditManager
    from core.sync_manager import SyncManager

    # Initialize managers
    data_manager = DataManager()
    transaction_manager = TransactionManager(data_manager)
    task_manager = TaskManager(data_manager)
    shop_manager = ShopManager(data_manager)
    announcement_manager = AnnouncementManager(data_manager)
    embed_builder = EmbedBuilder()
    cache_manager = CacheManager()
    auth_manager = AuthManager(data_manager)
    audit_manager = AuditManager(data_manager)
    sync_manager = SyncManager(data_manager)

    logger.info("✅ All managers initialized")
except ImportError as e:
    logger.warning(f"⚠️  Some managers not available: {e}")

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
        'timestamp': datetime.utcnow().isoformat(),
        'environment': 'production' if IS_PRODUCTION else 'development',
        'cors_enabled': True
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        'bot_status': 'online',
        'uptime': '0d 0h 0m',
        'servers': 0
    })

# ========== AUTHENTICATION ==========
@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'changeme123')

        if username == admin_username and password == admin_password:
            session['authenticated'] = True
            session['username'] = username
            session.permanent = True

            return jsonify({
                'success': True,
                'message': 'Login successful',
                'user': {'username': username}
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid username or password'
            }), 401

    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
def get_servers():
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        servers = data_manager.get_all_guilds()
        return jsonify({'servers': servers}), 200
    except Exception as e:
        logger.error(f"Error getting servers: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/config', methods=['GET'])
def get_server_config(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        config = data_manager.get_guild_config(server_id)
        return jsonify(config), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/config', methods=['PUT'])
def update_server_config(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        data_manager.update_guild_config(server_id, data)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/channels', methods=['GET'])
def get_channels(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        channels = data_manager.get_guild_channels(server_id)
        return jsonify({'channels': channels}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== USER MANAGEMENT ==========
@app.route('/api/<server_id>/users', methods=['GET'])
def get_users(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        users = data_manager.get_guild_users(server_id, page, limit)
        return jsonify(users), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/users/<user_id>', methods=['GET'])
def get_user(server_id, user_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        user = data_manager.get_user(server_id, user_id)
        return jsonify(user), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/users/<user_id>/balance', methods=['PUT'])
def update_balance(server_id, user_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        amount = data.get('amount', 0)
        transaction_manager.adjust_balance(server_id, user_id, amount, 'Admin adjustment')
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== TASK MANAGEMENT ==========
@app.route('/api/<server_id>/tasks', methods=['GET'])
def get_tasks(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        tasks = task_manager.get_tasks(server_id)
        return jsonify({'tasks': tasks}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/tasks', methods=['POST'])
def create_task(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        task = task_manager.create_task(server_id, data)
        return jsonify(task), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/tasks/<task_id>', methods=['PUT'])
def update_task(server_id, task_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        task_manager.update_task(server_id, task_id, data)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/tasks/<task_id>', methods=['DELETE'])
def delete_task(server_id, task_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        task_manager.delete_task(server_id, task_id)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== SHOP MANAGEMENT ==========
@app.route('/api/<server_id>/shop', methods=['GET'])
def get_shop(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        items = shop_manager.get_items(server_id)
        return jsonify({'items': items}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/shop', methods=['POST'])
def create_shop_item(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        item = shop_manager.create_item(server_id, data)
        return jsonify(item), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/shop/<item_id>', methods=['PUT'])
def update_shop_item(server_id, item_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        shop_manager.update_item(server_id, item_id, data)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/shop/<item_id>', methods=['DELETE'])
def delete_shop_item(server_id, item_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        shop_manager.delete_item(server_id, item_id)
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== TRANSACTIONS ==========
@app.route('/api/<server_id>/transactions', methods=['GET'])
def get_transactions(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        transactions = transaction_manager.get_transactions(server_id)
        return jsonify({'transactions': transactions}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== ANNOUNCEMENTS ==========
@app.route('/api/<server_id>/announcements', methods=['GET'])
def get_announcements(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        announcements = announcement_manager.get_announcements(server_id)
        return jsonify({'announcements': announcements}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/<server_id>/announcements', methods=['POST'])
def create_announcement(server_id):
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        announcement = announcement_manager.create_announcement(server_id, data)
        return jsonify(announcement), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
