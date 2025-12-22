#!/usr/bin/env python3
import requests
import sys
import json
import os

BRIDGE_URL = os.environ.get('AGORA_BRIDGE_URL', 'http://localhost:5018')

def test_provision(username, email):
    url = f"{BRIDGE_URL}/provision"
    payload = {
        "username": username,
        "email": email,
        "message": "Integration test from script"
    }
    
    print(f"Testing provisioning against {url}...")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload)
        print(f"\nStatus Code: {response.status_code}")
        try:
            data = response.json()
            print(f"Response Body:\n{json.dumps(data, indent=2)}")
        except:
            print(f"Response Body (text): {response.text}")
            
        if response.status_code == 201:
            print("\n✅ Success! Provisioning works.")
            print(f"URL: {data.get('repo_url')}")
            print(f"User: {data.get('username')}")
            print(f"Pass: {data.get('password')}")
        else:
            print("\n❌ Failed.")
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Could not connect to {BRIDGE_URL}. Is the bridge running?")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ./test_provision.py <username> <email>")
        print("Example: ./test_provision.py testuser1 test@example.com")
        sys.exit(1)
        
    username = sys.argv[1]
    email = sys.argv[2]
    test_provision(username, email)
