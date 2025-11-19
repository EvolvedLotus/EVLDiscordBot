#!/usr/bin/env python3
"""
Simple CORS test for local backend
"""
import os
import sys
import json
from flask import Flask, request, jsonify
from flask_cors import CORS

# Set minimal environment variables for testing
os.environ['JWT_SECRET_KEY'] = 'test_secret_key_for_cors_testing'
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'test_key'
os.environ['DISCORD_TOKEN'] = 'test_token'
os.environ['PORT'] = '5001'

# Import and test our backend CORS configuration
sys.path.insert(0, '.')
from backend import app

def test_cors_headers():
    """Test CORS headers in our Flask app"""
    print("Testing CORS configuration...")

    with app.test_client() as client:
        # Test OPTIONS preflight request
        print("\n1. Testing OPTIONS preflight request...")
        response = client.options('/api/auth/login',
                                headers={
                                    'Origin': 'https://evolvedlotus.github.io',
                                    'Access-Control-Request-Method': 'POST',
                                    'Access-Control-Request-Headers': 'Content-Type'
                                })

        print(f"Status: {response.status_code}")
        print("CORS Headers:")
        for header, value in response.headers.items():
            if header.lower().startswith('access-control'):
                print(f"  {header}: {value}")

        # Test POST request
        print("\n2. Testing POST request...")
        response = client.post('/api/auth/login',
                             headers={
                                 'Origin': 'https://evolvedlotus.github.io',
                                 'Content-Type': 'application/json'
                             },
                             data=json.dumps({
                                 'username': 'test',
                                 'password': 'test'
                             }))

        print(f"Status: {response.status_code}")
        print("CORS Headers:")
        for header, value in response.headers.items():
            if header.lower().startswith('access-control'):
                print(f"  {header}: {value}")

        # Test session cookie settings
        print("\n3. Testing session cookie configuration...")
        with app.test_request_context():
            from backend import session
            print("Session cookie settings:")
            print(f"  SESSION_COOKIE_SECURE: {app.config.get('SESSION_COOKIE_SECURE')}")
            print(f"  SESSION_COOKIE_SAMESITE: {app.config.get('SESSION_COOKIE_SAMESITE')}")
            print(f"  SESSION_COOKIE_HTTPONLY: {app.config.get('SESSION_COOKIE_HTTPONLY')}")

if __name__ == "__main__":
    test_cors_headers()
