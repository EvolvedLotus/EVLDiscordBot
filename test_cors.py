#!/usr/bin/env python3
"""
Test CORS configuration for Railway backend
"""
import requests
import json

def test_cors():
    """Test CORS preflight request"""
    url = "https://evldiscordbot-production.up.railway.app/api/auth/login"

    headers = {
        "Origin": "https://evolvedlotus.github.io",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type"
    }

    print("Testing CORS preflight request...")
    print(f"URL: {url}")
    print(f"Headers: {json.dumps(headers, indent=2)}")

    try:
        response = requests.options(url, headers=headers, timeout=10)

        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers:")
        for header, value in response.headers.items():
            print(f"  {header}: {value}")

        # Check CORS headers
        cors_headers = {
            'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
            'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
            'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers'),
            'Access-Control-Allow-Credentials': response.headers.get('Access-Control-Allow-Credentials')
        }

        print(f"\nCORS Headers:")
        for header, value in cors_headers.items():
            status = "✅" if value else "❌"
            print(f"  {status} {header}: {value}")

        # Validate CORS configuration
        if cors_headers['Access-Control-Allow-Origin'] == 'https://evolvedlotus.github.io':
            print("\n✅ CORS Origin is correctly configured")
        else:
            print(f"\n❌ CORS Origin mismatch. Expected: https://evolvedlotus.github.io, Got: {cors_headers['Access-Control-Allow-Origin']}")

        if 'POST' in cors_headers['Access-Control-Allow-Methods'] or cors_headers['Access-Control-Allow-Methods'] == '*':
            print("✅ POST method is allowed")
        else:
            print(f"❌ POST method not allowed. Methods: {cors_headers['Access-Control-Allow-Methods']}")

        if 'Content-Type' in cors_headers['Access-Control-Allow-Headers'] or cors_headers['Access-Control-Allow-Headers'] == '*':
            print("✅ Content-Type header is allowed")
        else:
            print(f"❌ Content-Type header not allowed. Headers: {cors_headers['Access-Control-Allow-Headers']}")

        if cors_headers['Access-Control-Allow-Credentials'] == 'true':
            print("✅ Credentials are allowed")
        else:
            print("❌ Credentials are not allowed")

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

def test_login_endpoint():
    """Test actual login endpoint"""
    url = "https://evldiscordbot-production.up.railway.app/api/auth/login"

    headers = {
        "Origin": "https://evolvedlotus.github.io",
        "Content-Type": "application/json"
    }

    data = {
        "username": "test",
        "password": "test"
    }

    print(f"\n\nTesting login endpoint...")
    print(f"URL: {url}")
    print(f"Data: {json.dumps(data)}")

    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)

        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Headers:")
        for header, value in response.headers.items():
            if header.lower().startswith('access-control'):
                print(f"  {header}: {value}")

        try:
            response_data = response.json()
            print(f"Response Data: {json.dumps(response_data, indent=2)}")
        except:
            print(f"Response Text: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    test_cors()
    test_login_endpoint()
