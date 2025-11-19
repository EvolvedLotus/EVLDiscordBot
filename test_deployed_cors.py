#!/usr/bin/env python3
"""
Test if Railway deployment has CORS properly configured
Run: python test_deployed_cors.py
"""

import requests
import sys

def test_cors():
    """Test CORS configuration on deployed backend"""

    backend_url = 'https://evldiscordbot-production.up.railway.app'
    frontend_origin = 'https://evolvedlotus.github.io'

    print("="*60)
    print("🧪 Testing CORS Configuration on Railway")
    print("="*60)
    print(f"Backend: {backend_url}")
    print(f"Origin: {frontend_origin}")
    print()

    # Test 1: Health Check
    print("📋 Test 1: Health Check")
    print("-"*60)
    try:
        response = requests.get(f"{backend_url}/api/health", timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        if response.status_code != 200:
            print("❌ Health check failed!")
            return False
        print("✅ Health check passed")
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

    print()

    # Test 2: OPTIONS Preflight Request
    print("📋 Test 2: CORS Preflight (OPTIONS)")
    print("-"*60)
    try:
        response = requests.options(
            f"{backend_url}/api/auth/login",
            headers={
                'Origin': frontend_origin,
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type'
            },
            timeout=10
        )

        print(f"Status: {response.status_code}")
        print()
        print("Response Headers:")
        for header, value in response.headers.items():
            if 'access-control' in header.lower():
                print(f"  {header}: {value}")

        # Check for required CORS headers
        allow_origin = response.headers.get('Access-Control-Allow-Origin')
        allow_credentials = response.headers.get('Access-Control-Allow-Credentials')
        allow_methods = response.headers.get('Access-Control-Allow-Methods')
        allow_headers = response.headers.get('Access-Control-Allow-Headers')

        print()
        print("CORS Header Validation:")

        if allow_origin == frontend_origin:
            print(f"  ✅ Access-Control-Allow-Origin: {allow_origin}")
        elif allow_origin:
            print(f"  ⚠️  Access-Control-Allow-Origin: {allow_origin} (expected: {frontend_origin})")
        else:
            print(f"  ❌ Access-Control-Allow-Origin: MISSING")
            print()
            print("⚠️  THIS IS THE PROBLEM!")
            print("The backend is not sending CORS headers.")
            print()
            print("Possible causes:")
            print("  1. flask-cors not installed in requirements.txt")
            print("  2. CORS configuration code not in backend.py")
            print("  3. Old code still deployed (need to redeploy)")
            print("  4. Backend crashed during startup")
            return False

        if allow_credentials and allow_credentials.lower() == 'true':
            print(f"  ✅ Access-Control-Allow-Credentials: {allow_credentials}")
        else:
            print(f"  ❌ Access-Control-Allow-Credentials: {allow_credentials or 'MISSING'}")

        if allow_methods:
            print(f"  ✅ Access-Control-Allow-Methods: {allow_methods}")
        else:
            print(f"  ❌ Access-Control-Allow-Methods: MISSING")

        if allow_headers:
            print(f"  ✅ Access-Control-Allow-Headers: {allow_headers}")
        else:
            print(f"  ❌ Access-Control-Allow-Headers: MISSING")

        print()

        if response.status_code == 200 and allow_origin == frontend_origin and allow_credentials:
            print("✅ CORS preflight test PASSED")
            return True
        else:
            print("❌ CORS preflight test FAILED")
            return False

    except Exception as e:
        print(f"❌ Preflight error: {e}")
        return False

    print()

if __name__ == '__main__':
    print()
    success = test_cors()
    print()
    print("="*60)
    if success:
        print("🎉 ALL TESTS PASSED - CORS is configured correctly!")
        print()
        print("Next steps:")
        print("  1. Clear your browser cache")
        print("  2. Go to https://evolvedlotus.github.io")
        print("  3. Try logging in")
        print("  4. CORS errors should be gone!")
    else:
        print("❌ TESTS FAILED - CORS is NOT configured correctly")
        print()
        print("Action required:")
        print("  1. Ensure flask-cors is in requirements.txt")
        print("  2. Add CORS configuration to backend.py (see artifact)")
        print("  3. Commit and push changes")
        print("  4. Wait for Railway to deploy")
        print("  5. Run this test again")
    print("="*60)
    print()

    sys.exit(0 if success else 1)
