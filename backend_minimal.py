"""
MINIMAL BACKEND WITH CORS - For Railway deployment testing
This is a stripped-down version with just CORS and basic endpoints
"""

from flask import Flask, request, make_response, jsonify
from flask_cors import CORS
import os

print("="*50)
print("🚀 MINIMAL BACKEND STARTING")
print("="*50)

app = Flask(__name__)

# ========== CRITICAL: CORS MUST BE CONFIGURED FIRST ==========
# Detect environment
IS_PRODUCTION = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('ENVIRONMENT') == 'production'
IS_DEVELOPMENT = not IS_PRODUCTION

print(f"🌍 Environment: {'PRODUCTION' if IS_PRODUCTION else 'DEVELOPMENT'}")
print(f"🌍 RAILWAY_ENVIRONMENT: {os.getenv('RAILWAY_ENVIRONMENT')}")
print(f"🌍 ENVIRONMENT: {os.getenv('ENVIRONMENT')}")

# Define allowed origins based on environment
if IS_PRODUCTION:
    ALLOWED_ORIGINS = [
        'https://evolvedlotus.github.io',
        'https://evldiscordbot-production.up.railway.app',
    ]
else:
    ALLOWED_ORIGINS = [
        'http://localhost:3000',
        'http://localhost:5000',
        'http://localhost:8000',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:5000',
        'http://127.0.0.1:8000',
        'https://evolvedlotus.github.io',
    ]

print(f"🔒 CORS Origins: {ALLOWED_ORIGINS}")

# Initialize CORS - THIS MUST HAPPEN BEFORE ROUTES
CORS(app,
     origins=ALLOWED_ORIGINS,
     supports_credentials=True,
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'],
     expose_headers=['Content-Type', 'X-Total-Count'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
     max_age=3600
)

print("✅ CORS initialized with flask-cors")

# ========== SESSION CONFIGURATION ==========
app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'dev-secret-key')

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

print(f"🍪 Session Cookie Config: Secure={app.config['SESSION_COOKIE_SECURE']}")

# ========== AFTER_REQUEST HANDLER FOR CORS ==========
@app.after_request
def after_request_cors(response):
    """Ensure CORS headers on ALL responses"""
    origin = request.headers.get('Origin')

    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Type, X-Total-Count'
        print(f"✅ Added CORS headers for origin: {origin}")
    else:
        print(f"⚠️  Origin not in allowed list: {origin}")

    return response

# ========== EXPLICIT OPTIONS HANDLER ==========
@app.route('/<path:path>', methods=['OPTIONS'])
@app.route('/api/<path:path>', methods=['OPTIONS'])
def handle_options(path=None):
    """Handle preflight requests"""
    origin = request.headers.get('Origin')

    print(f"🔍 OPTIONS preflight for path: /{path}")
    print(f"🔍 Origin: {origin}")

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
        print(f"✅ Preflight approved for origin: {origin}")
        return response

    print(f"❌ Preflight rejected for origin: {origin}")
    return make_response('Forbidden', 403)

# ========== TEST ENDPOINT ==========
@app.route('/api/test-cors', methods=['GET', 'OPTIONS'])
def test_cors():
    """Test endpoint to verify CORS is working"""
    return jsonify({
        'message': 'CORS is working!',
        'environment': 'production' if IS_PRODUCTION else 'development',
        'allowed_origins': ALLOWED_ORIGINS
    })

# ========== HEALTH CHECK ==========
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'cors_enabled': True,
        'environment': 'production' if IS_PRODUCTION else 'development',
        'message': 'Minimal backend with CORS is running'
    })

print("="*50)
print("✅ MINIMAL BACKEND STARTUP COMPLETE")
print("="*50)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting minimal backend on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
