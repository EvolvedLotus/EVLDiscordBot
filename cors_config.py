"""
CORS Configuration Module
Handles all CORS setup for Flask app
Updated: 2025-11-17 - Manual CORS implementation
"""

ALLOWED_ORIGINS = [
    'https://evolvedlotus.github.io',
    'https://evolvedlotus.github.io/EVLDiscordBot/',
    'http://localhost:5500',
    'http://127.0.0.1:5500',
    'http://localhost:3000',
    'http://127.0.0.1:3000'
]

def setup_cors(app):
    """
    Configure CORS manually for Railway compatibility
    """
    print("=" * 60)
    print("🌐 SETTING UP MANUAL CORS")
    print("=" * 60)
    print(f"Allowed Origins: {ALLOWED_ORIGINS}")

    @app.after_request
    def add_cors_headers(response):
        """Add CORS headers to all responses"""
        origin = request.headers.get('Origin')

        # Check if origin is allowed
        if origin and origin in ALLOWED_ORIGINS:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            print(f"✅ CORS allowed for origin: {origin}")
        elif not origin:
            # Allow requests without Origin header (for same-origin or direct access)
            response.headers['Access-Control-Allow-Origin'] = '*'
            print("✅ CORS allowed for request without Origin")

        # Always add these headers
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Max-Age'] = '3600'

        return response

    @app.before_request
    def handle_options():
        """Handle preflight OPTIONS requests"""
        if request.method == 'OPTIONS':
            origin = request.headers.get('Origin')
            if origin and origin in ALLOWED_ORIGINS:
                response = app.response_class()
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Credentials'] = 'true'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
                response.headers['Access-Control-Max-Age'] = '3600'
                print(f"✅ Preflight OPTIONS handled for: {origin}")
                return response, 200
            else:
                print(f"❌ Preflight OPTIONS rejected for: {origin}")
                return {'error': 'CORS not allowed'}, 403

    print("✅ Manual CORS configured successfully")
    print("=" * 60)

    return app
