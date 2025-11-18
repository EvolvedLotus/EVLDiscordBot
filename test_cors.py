"""
Minimal CORS test - bypasses all your existing code
"""
from flask import Flask, request, jsonify, make_response
import os

print("=" * 80)
print("🧪 MINIMAL CORS TEST SERVER STARTING...")
print("=" * 80)

try:
    app = Flask(__name__)
    print("✅ Flask app created successfully")
except Exception as e:
    print(f"❌ Failed to create Flask app: {e}")
    exit(1)

ALLOWED_ORIGIN = 'https://evolvedlotus.github.io'
print(f"Allowed Origin: {ALLOWED_ORIGIN}")
print("=" * 80)

@app.before_request
def handle_options():
    """Handle ALL OPTIONS requests FIRST"""
    if request.method == 'OPTIONS':
        print(f"🔵 OPTIONS request from: {request.headers.get('Origin')}")
        response = make_response('', 204)
        response.headers['Access-Control-Allow-Origin'] = ALLOWED_ORIGIN
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Requested-With'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '3600'
        print(f"✅ Sent CORS headers")
        return response

@app.after_request
def add_cors_headers(response):
    """Add CORS headers to ALL responses"""
    origin = request.headers.get('Origin')
    if origin == ALLOWED_ORIGIN:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        print(f"✅ Added CORS headers to response")
    return response

@app.route('/api/test', methods=['GET', 'POST', 'OPTIONS'])
def test():
    """Simple test endpoint"""
    print(f"🟢 {request.method} request from: {request.headers.get('Origin')}")
    return jsonify({
        'success': True,
        'message': 'CORS is working!',
        'method': request.method
    })

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    """Minimal login endpoint"""
    print(f"🔐 LOGIN {request.method} from: {request.headers.get('Origin')}")

    if request.method == 'OPTIONS':
        return '', 204

    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    print(f"Username: {username}, Password provided: {bool(password)}")

    # Minimal validation
    if username == os.environ.get('ADMIN_USERNAME') and password == os.environ.get('ADMIN_PASSWORD'):
        return jsonify({'success': True, 'message': 'Login successful'})

    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

if __name__ == '__main__':
    try:
        port_str = os.environ.get('PORT', '8080')
        print(f"PORT environment variable: '{port_str}'")
        port = int(port_str)
        print(f"Parsed port as: {port}")
    except (ValueError, TypeError) as e:
        print(f"❌ Invalid PORT value '{port_str}', using default 8080: {e}")
        port = 8080

    print(f"🚀 Starting Flask server on 0.0.0.0:{port}")
    try:
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        print(f"❌ Failed to start Flask server: {e}")
        exit(1)
