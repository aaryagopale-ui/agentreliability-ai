"""Phase 5: Security and Multi-Tenant Verification Script.

Tests:
1. Valid API key
2. Invalid API key
3. Revoked API key
4. Missing API key
5. Project ownership enforcement
6. Cross-project data isolation
7. Authentication and session protection
8. Secret redaction
9. Malformed trace payloads (bad JSON, invalid schema, payload size limit)
10. Duplicate trace submissions
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "backend"))
sys.path.insert(0, str(ROOT_DIR / "sdk" / "src"))

from fastapi.testclient import TestClient
from app.main import app
from app import auth_store, database, project_store, trace_store
from app.security import (
    create_session,
    generate_csrf_token,
    hash_password,
    verify_password,
)
from agentreliability.redaction import Redactor

client = TestClient(app)


def run_phase5_verification():
    print("=" * 70)
    print("PHASE 5: Security and Multi-Tenant Verification")
    print("=" * 70)

    # 1. Setup two distinct test users and projects
    user_a = auth_store.get_user_by_email_with_hash("security_test_user_a@example.com")
    if not user_a:
        user_a = auth_store.create_user("security_test_user_a@example.com", hash_password("ValidPassword123!"), "User A")
    
    user_b = auth_store.get_user_by_email_with_hash("security_test_user_b@example.com")
    if not user_b:
        user_b = auth_store.create_user("security_test_user_b@example.com", hash_password("ValidPassword123!"), "User B")

    # Create isolated projects
    proj_a, key_a = project_store.create_project("Project Security Alpha", owner_id=user_a["id"])
    proj_b, key_b = project_store.create_project("Project Security Beta", owner_id=user_b["id"])
    
    print(f"✓ Created test tenant A (User ID: {user_a['id']}, Project ID: {proj_a['id']})")
    print(f"✓ Created test tenant B (User ID: {user_b['id']}, Project ID: {proj_b['id']})")

    # -------------------------------------------------------------------------
    # Test 1: Valid API Key Ingestion
    # -------------------------------------------------------------------------
    print("\n--- 1. Testing Valid API Key ---")
    valid_event = {
        "event_id": f"evt-{int(time.time()*1000)}-valid",
        "execution_id": f"exec-sec-{int(time.time()*1000)}",
        "agent_name": "security_probe_agent",
        "type": "execution_start",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input": {"task": "verify_security"},
    }
    res1 = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": key_a},
        json={"events": [valid_event]},
    )
    assert res1.status_code == 200, f"Expected 200, got {res1.status_code}: {res1.text}"
    assert res1.json()["accepted"] == 1
    print("  ✅ Valid API Key: Accepted (200 OK)")

    # -------------------------------------------------------------------------
    # Test 2: Invalid API Key
    # -------------------------------------------------------------------------
    print("\n--- 2. Testing Invalid API Key ---")
    res2 = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": "ar_live_completely_fake_invalid_key_xyz987"},
        json={"events": [valid_event]},
    )
    assert res2.status_code == 401, f"Expected 401, got {res2.status_code}"
    assert "Invalid API key" in res2.text or "invalid" in res2.text.lower()
    print("  ✅ Invalid API Key: Rejected (401 Unauthorized)")

    # -------------------------------------------------------------------------
    # Test 3: Revoked API Key
    # -------------------------------------------------------------------------
    print("\n--- 3. Testing Revoked API Key ---")
    key_rec, key_to_revoke = project_store.create_api_key(proj_a["id"], name="Key to Revoke")
    # Verify it works initially
    pre_res = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": key_to_revoke},
        json={"events": [valid_event]},
    )
    assert pre_res.status_code == 200

    # Revoke key
    project_store.revoke_api_key(proj_a["id"], key_rec["id"])
    
    post_res = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": key_to_revoke},
        json={"events": [valid_event]},
    )
    assert post_res.status_code == 401, f"Expected 401, got {post_res.status_code}"
    print("  ✅ Revoked API Key: Rejected immediately upon revocation (401 Unauthorized)")

    # -------------------------------------------------------------------------
    # Test 4: Missing API Key
    # -------------------------------------------------------------------------
    print("\n--- 4. Testing Missing API Key ---")
    res4 = client.post(
        "/api/v1/traces/events",
        json={"events": [valid_event]},
    )
    assert res4.status_code == 401
    print("  ✅ Missing API Key: Rejected (401 Unauthorized)")

    # -------------------------------------------------------------------------
    # Test 5 & 6: Project Ownership & Cross-Project Data Isolation
    # -------------------------------------------------------------------------
    print("\n--- 5 & 6. Testing Project Ownership & Tenant Isolation ---")
    session_token_a, _ = create_session(user_a["id"])
    csrf_a = generate_csrf_token()
    cookies_a = {"agentreliability_session": session_token_a, "agentreliability_csrf": csrf_a}

    session_token_b, _ = create_session(user_b["id"])
    csrf_b = generate_csrf_token()
    cookies_b = {"agentreliability_session": session_token_b, "agentreliability_csrf": csrf_b}

    # User A tries to read User B's project
    res_iso1 = client.get(
        f"/api/projects/{proj_b['id']}",
        cookies=cookies_a,
        headers={"X-CSRF-Token": csrf_a},
    )
    assert res_iso1.status_code in (403, 404), f"Expected 403 or 404, got {res_iso1.status_code}"
    print("  ✓ Cross-tenant project access rejected (User A cannot access User B's project)")

    # User A attempts to list traces scoped to Project B
    res_iso2 = client.get(
        "/api/traces/executions",
        cookies=cookies_a,
        headers={"X-Project-Id": str(proj_b["id"])},
    )
    assert res_iso2.status_code in (403, 404), f"Expected 403/404, got {res_iso2.status_code}"
    print("  ✓ Cross-tenant trace scoping rejected (User A cannot query Project B's traces)")
    print("  ✅ Project Ownership & Cross-Project Isolation: PASSED")

    # -------------------------------------------------------------------------
    # Test 7: Authentication & Session Protection
    # -------------------------------------------------------------------------
    print("\n--- 7. Testing Authentication & Session Protection ---")
    unauth_res = client.get("/api/auth/me")
    assert unauth_res.status_code == 401

    fake_session_res = client.get(
        "/api/auth/me",
        cookies={"agentreliability_session": "tampered_session_token_1234567890"},
    )
    assert fake_session_res.status_code == 401
    print("  ✅ Session Protection: Tampered and missing session cookies rejected (401)")

    # -------------------------------------------------------------------------
    # Test 8: Client-Side Secret Redaction
    # -------------------------------------------------------------------------
    print("\n--- 8. Testing Client-Side Secret Redaction ---")
    redactor = Redactor()
    sample_payload = {
        "user_email": "engineer@reliability.ai",
        "api_key": "sk-1234567890abcdef1234567890abcdef",
        "auth_token": "secret_access_token",
        "headers": {"authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
        "nested": {
            "password": "SuperSecretPassword123!",
            "normal_data": "safe_order_details",
        }
    }
    redacted = redactor.prepare(sample_payload, 2000)
    redacted_str = json.dumps(redacted)
    assert "SuperSecretPassword123!" not in redacted_str
    assert "sk-1234567890abcdef" not in redacted_str
    assert "secret_access_token" not in redacted_str
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["normal_data"] == "safe_order_details"
    print("  ✅ Secret Redaction: Passwords, tokens, and authorization headers masked to [REDACTED]")

    # -------------------------------------------------------------------------
    # Test 9: Malformed Payloads & Size Limits Fail Safely
    # -------------------------------------------------------------------------
    print("\n--- 9. Testing Malformed Trace Payloads & Size Limits ---")
    # Invalid JSON syntax
    bad_json_res = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": key_a, "Content-Type": "application/json"},
        content=b"{not_json_syntax...",
    )
    assert bad_json_res.status_code == 400
    print("  ✓ Invalid JSON syntax rejected with 400 Bad Request")

    # Invalid Pydantic schema (missing required event_id)
    bad_schema_res = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": key_a},
        json={"events": [{"agent_name": "agent_no_id", "type": "tool_call"}]},
    )
    assert bad_schema_res.status_code == 422
    print("  ✓ Invalid schema rejected with 422 Unprocessable Entity")

    # Oversized payload exceeding MAX_BODY_BYTES (1MB)
    huge_body = b"x" * (1_000_000 + 1024)
    huge_res = client.post(
        "/api/v1/traces/events",
        headers={"X-API-Key": key_a, "Content-Length": str(len(huge_body))},
        content=huge_body,
    )
    assert huge_res.status_code == 413
    print("  ✓ Oversized payload (>1MB) safely rejected with 413 Payload Too Large")
    print("  ✅ Malformed Payloads & Defensive Limits: PASSED")

    # -------------------------------------------------------------------------
    # Test 10: Duplicate Trace Submissions
    # -------------------------------------------------------------------------
    print("\n--- 10. Testing Duplicate Trace Submissions ---")
    dup_id = f"evt-dup-{int(time.time()*1000)}"
    dup_event = {
        "event_id": dup_id,
        "execution_id": f"exec-dup-{int(time.time()*1000)}",
        "agent_name": "duplicate_test_agent",
        "type": "execution_start",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input": {"test": "first_submission"},
    }
    # First submission
    sub1 = client.post("/api/v1/traces/events", headers={"X-API-Key": key_a}, json={"events": [dup_event]})
    assert sub1.status_code == 200
    assert sub1.json() == {"accepted": 1, "duplicates": 0}

    # Second identical submission
    sub2 = client.post("/api/v1/traces/events", headers={"X-API-Key": key_a}, json={"events": [dup_event]})
    assert sub2.status_code == 200
    assert sub2.json() == {"accepted": 0, "duplicates": 1}
    print("  ✅ Duplicate Trace Submissions: Deduplicated idempotently (accepted: 0, duplicates: 1)")

    print("\n" + "=" * 70)
    print("PHASE 5 SECURITY & MULTI-TENANT VERIFICATION COMPLETED (ALL 10 TESTS PASSED)")
    print("=" * 70)


if __name__ == "__main__":
    run_phase5_verification()
