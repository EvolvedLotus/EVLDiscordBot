#!/usr/bin/env python3
"""
Simple test script to verify SSE keepalive functionality
"""
import requests
import time
import threading

def test_sse_keepalive():
    """Test SSE keepalive by connecting and monitoring for keepalive messages"""
    print("Testing SSE keepalive functionality...")

    try:
        # Connect to SSE endpoint
        response = requests.get('http://localhost:5000/api/stream', stream=True, timeout=40)

        if response.status_code != 200:
            print(f"Failed to connect to SSE endpoint: {response.status_code}")
            return

        print("Connected to SSE endpoint. Waiting for keepalive messages...")

        keepalive_count = 0
        start_time = time.time()

        for line in response.iter_lines():
            if time.time() - start_time > 35:  # Test for 35 seconds
                break

            if line:
                line_str = line.decode('utf-8')
                if 'keepalive' in line_str:
                    keepalive_count += 1
                    print(f"✓ Received keepalive message #{keepalive_count}: {line_str}")

                elif 'connected' in line_str:
                    print(f"✓ Connection established: {line_str}")

                elif 'heartbeat' in line_str:
                    print(f"✓ Received heartbeat: {line_str}")

        print(f"\nTest completed. Received {keepalive_count} keepalive messages in {time.time() - start_time:.1f} seconds")

        if keepalive_count > 0:
            print("✅ SSE keepalive functionality is working!")
        else:
            print("❌ No keepalive messages received")

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to SSE endpoint: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    test_sse_keepalive()
