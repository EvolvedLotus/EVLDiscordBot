#!/usr/bin/env python3
"""
Simple CORS test script that doesn't require environment variables
"""
import requests
import json

def test_cors_simple():
    """Test CORS configuration with a simple Flask app"""

    # Test the CORS test endpoint
    test_url = "https://evldiscordbot-production.up.railway.app/api/test-cors"

    print("Testing CORS configuration...")
    print(f"URL: {test_url}")

    try:
        # Test GET request
        response = requests.get(test_url, headers={
            'Origin': 'https://evolvedlotus.github.io'
        }, timeout=10)

        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        # Check CORS headers
        cors_headers = {
            'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
            'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
            'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers'),
            'Access-Control-Allow-Credentials': response.headers.get('Access-Control-Allow-Credentials')
        }

        print("\nCORS Headers:")
        for header, value in cors_headers.items():
            status = "✅" if value else "❌"
            print(f"  {status} {header}: {value}")

        # Check if origin is allowed
        allowed_origin = cors_headers['Access-Control-Allow-Origin']
        if allowed_origin == 'https://evolvedlotus.github.io':
            print("\n✅ CORS configuration looks correct!")
            return True
        else:
            print(f"\n❌ CORS origin mismatch. Expected: https://evolvedlotus.github.io, Got: {allowed_origin}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False

if __name__ == "__main__":
    test_cors_simple()
