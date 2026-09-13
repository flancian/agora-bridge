#!/usr/bin/env python3
"""
Tests for the /sources endpoint in agora-bridge, validating:
- Required payload fields
- Anti-spam honeypot detection
- Directory traversal & format safety
- Git repository proof-of-work (rejects invalid/non-git spam URLs)
- Duplicate URL & target detection
"""

import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from api import create_app

def run_tests():
    app = create_app()
    client = app.test_client()

    print("Running tests for /sources endpoint...")

    # 1. Missing fields
    res = client.post('/sources', json={})
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    print("✅ Test 1: Missing fields rejected with 400")

    # 2. Honeypot check
    res = client.post('/sources', json={
        'url': 'https://example.com',
        'target': 'garden/botuser',
        'type': 'garden',
        'honeypot': 'spam_bot'
    })
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    print("✅ Test 2: Honeypot submission rejected with 400")

    # 3. Directory traversal in target
    res = client.post('/sources', json={
        'url': 'https://example.com',
        'target': 'garden/../../etc/passwd',
        'type': 'garden'
    })
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    print("✅ Test 3: Path traversal target rejected with 400")

    # 4. Target prefix mismatch
    res = client.post('/sources', json={
        'url': 'https://example.com',
        'target': 'garden/alice',
        'type': 'stoa'
    })
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    print("✅ Test 4: Target/type mismatch rejected with 400")

    # 5. Proof-of-work rejection for spam non-git URL
    res = client.post('/sources', json={
        'url': 'https://drakashintervention.com/book-an-appointment/',
        'target': 'garden/drakash',
        'type': 'garden'
    })
    assert res.status_code == 400, f"Expected 400, got {res.status_code}"
    data = res.get_json()
    assert 'Proof of work failed' in data.get('error', ''), f"Expected proof of work error, got {data}"
    print("✅ Test 5: Spam non-git URL rejected by git proof-of-work with 400")

    # 6. Duplicate URL rejection
    res = client.post('/sources', json={
        'url': 'https://github.com/goldfishlaser/dev-notes',
        'target': 'garden/testunique123',
        'type': 'garden'
    })
    assert res.status_code == 409, f"Expected 409, got {res.status_code}"
    print("✅ Test 6: Duplicate URL rejected with 409")

    # 7. Duplicate target rejection
    res = client.post('/sources', json={
        'url': 'https://github.com/torvalds/linux',
        'target': 'garden/goldfishlaser',
        'type': 'garden'
    })
    assert res.status_code == 409, f"Expected 409, got {res.status_code}"
    print("✅ Test 7: Duplicate target rejected with 409")

    print("\n🎉 All /sources validation and security tests PASSED!")

if __name__ == '__main__':
    run_tests()
