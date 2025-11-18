"""
CORS Configuration Module
Handles all CORS setup for Flask app
Updated: 2025-11-17 - Force redeploy
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
    Configure CORS for Flask app
    Must be called BEFORE any route definitions
    """
    from flask_cors import CORS

    print("=" * 60)
    print("🌐 SETTING UP CORS")
    print("=" * 60)
    print(f"Allowed Origins: {ALLOWED_ORIGINS}")

    # Enable CORS with explicit configuration
    CORS(
        app,
        resources={
            r"/*": {
                "origins": ALLOWED_ORIGINS,
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
                "expose_headers": ["Content-Type", "Authorization"],
                "supports_credentials": True,
                "max_age": 3600
            }
        }
    )

    print("✅ CORS configured successfully")
    print("=" * 60)

    # Add response handler to log CORS
    @app.after_request
    def log_cors_headers(response):
        origin = app.config.get('REQUEST_ORIGIN')
        if origin:
            print(f"📤 Response to {origin}: CORS headers present = {bool(response.headers.get('Access-Control-Allow-Origin'))}")
        return response

    @app.before_request
    def store_origin():
        from flask import request
        app.config['REQUEST_ORIGIN'] = request.headers.get('Origin')

    return app
