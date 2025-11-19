#!/usr/bin/env python3
"""
Test if backend can start with CORS configuration
"""

from flask import Flask, request, make_response, jsonify
from flask_cors import CORS
import os

print("="*50)
print("🚀 TESTING BACKEND STARTUP")
print("="*50)

app = Flask(__name__)

# Detect environment
IS_PRODUCTION = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('ENVIRONMENT') == 'production'
IS_DEVELOPMENT = not IS_PRODUCTION

print(f"🌍 Environment: {'PRODUCTION' if IS_PRODUCTION else 'DEVELOPMENT'}")

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

# Initialize CORS
CORS(app,
     origins=ALLOWED_ORIGINS,
     supports_credentials=True,
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'],
     expose_headers=['Content-Type', 'X-Total-Count'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
     max_age=3600
)

print("✅ CORS initialized")

# Test endpoint
@app.route('/api/test-cors', methods=['GET', 'OPTIONS'])
def test_cors():
    return jsonify({
        'message': 'CORS is working!',
        'environment': 'production' if IS_PRODUCTION else 'development',
        'allowed_origins': ALLOWED_ORIGINS
    })

print("="*50)
print("✅ BACKEND STARTUP TEST COMPLETE")
print("Backend should be able to start with CORS configuration")
print("="*50)

if __name__ == '__main__':
    print("Starting test server...")
    app.run(host='0.0.0.0', port=5001, debug=False)
