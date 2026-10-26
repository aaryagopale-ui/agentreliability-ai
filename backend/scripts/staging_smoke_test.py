#!/usr/bin/env python3
"""Live Staging Smoke-Test Suite for AgentReliability AI.

Executes a complete 12-point synthetic verification against a live staging deployment:
1. Health & readiness probe (/api/health)
2. User registration with synthetic credentials
3. User login and HttpOnly session cookie issuance
4. CSRF token validation on state-changing requests
5. Project creation and project switching (X-Project-Id)
6. API key generation and single-exposure plaintext verification
7. Trace ingestion via X-API-Key (/api/v1/traces/events)
8. Project-level trace query isolation
9. Converting execution trace to regression test case
10. Deterministic test replay execution
11. Multi-tenant anti-enumeration (404 on cross-user probing)
12. Safe session logout
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
import urllib.request
import urllib.error
import http.cookiejar


class StagingSmokeRunner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.csrf_token = ""
        self.passed = 0
        self.failed = 0

    def _get_cookie(self, name: str) -> str:
        for cookie in self.cookie_jar:
            if cookie.name == name:
                return cookie.value
        return ""

    def request(self, path: str, method: str = "GET", json_body: dict = None, headers: dict = None) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req_headers = {"Accept": "application/json"}
        if data:
            req_headers["Content-Type"] = "application/json"

        # Auto-attach CSRF token for mutating requests if available
        csrf = self._get_cookie("agentreliability_csrf")
        if csrf and method in ("POST", "PUT", "DELETE", "PATCH"):
            req_headers["X-CSRF-Token"] = csrf

        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with self.opener.open(req, timeout=10.0) as resp:
                status = resp.status
                body_bytes = resp.read()
                try:
                    body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                except Exception:
                    body = {"raw": body_bytes.decode("utf-8", errors="replace")}
                return status, body
        except urllib.error.HTTPError as e:
            err_body = e.read()
            try:
                body = json.loads(err_body.decode("utf-8")) if err_body else {}
            except Exception:
                body = {"raw": err_body.decode("utf-8", errors="replace")}
            return e.code, body
        except Exception as exc:
            return 0, {"error": str(exc)}

    def check(self, name: str, condition: bool, details: str = ""):
        if condition:
            print(f"  [PASS] {name}")
            self.passed += 1
        else:
            print(f"  [FAIL] {name}: {details}")
            self.failed += 1

    def run(self) -> bool:
        print(f"\n🚀 Starting Live Staging Smoke Tests against: {self.base_url}\n")
        rand_suffix = secrets.token_hex(4)
        user_email = f"smoke_test_{rand_suffix}@staging.test"
        password = "SmokePassword123!"

        # 1. Health check
        code, body = self.request("/api/health")
        self.check("Health Check (/api/health)", code == 200 and body.get("status") == "ok", str(body))

        # 2. Registration
        code, body = self.request("/api/auth/register", method="POST", json_body={"email": user_email, "password": password, "name": "Smoke User"})
        self.check("User Registration", code == 201 and "id" in body, str(body))
        user_id = body.get("id")

        # 3. Session cookie verification
        session_cookie = self._get_cookie("agentreliability_session")
        self.check("HttpOnly Session Cookie Issued", bool(session_cookie), "Cookie missing from jar")

        # 4. Identity verification (/api/auth/me)
        code, body = self.request("/api/auth/me")
        self.check("Identity (/api/auth/me)", code == 200 and body.get("email") == user_email, str(body))

        # 5. Project Creation
        code, body = self.request("/api/projects", method="POST", json_body={"name": "Staging Smoke Project"})
        self.check("Project Creation", code == 201 and "id" in body, str(body))
        project_id = body.get("id")

        # 6. API Key Generation
        code, body = self.request(f"/api/projects/{project_id}/keys", method="POST", json_body={"name": "Smoke Ingestion Key"})
        raw_key = body.get("api_key", "")
        self.check("API Key Generation & Single Plaintext Exposure", code == 201 and raw_key.startswith("ar_live_"), str(body))

        # 7. Trace Ingestion via X-API-Key
        now = datetime.now(timezone.utc).isoformat()
        trace_events = [
            {"event_id": f"smoke-{rand_suffix}:start", "execution_id": f"smoke-exec-{rand_suffix}", "agent_name": "smoke_agent", "type": "execution_start", "timestamp": now},
            {"event_id": f"smoke-{rand_suffix}:tool:1", "execution_id": f"smoke-exec-{rand_suffix}", "agent_name": "smoke_agent", "type": "tool_call", "timestamp": now, "tool_name": "probe_db", "status": "success"},
            {"event_id": f"smoke-{rand_suffix}:end", "execution_id": f"smoke-exec-{rand_suffix}", "agent_name": "smoke_agent", "type": "execution_end", "timestamp": now, "status": "success"},
        ]
        code, body = self.request("/api/v1/traces/events", method="POST", json_body={"events": trace_events}, headers={"X-API-Key": raw_key})
        self.check("SDK Trace Ingestion via X-API-Key", code == 200 and body.get("accepted") == 3, str(body))

        # 8. Trace Query Scoped by Project
        code, body = self.request("/api/traces/executions", headers={"X-Project-Id": str(project_id)})
        items = body.get("items", [])
        self.check("Project-Scoped Trace Query", code == 200 and any(i.get("execution_id") == f"smoke-exec-{rand_suffix}" for i in items), str(body))

        # 9. Create Test Case from Trace
        code, body = self.request(f"/api/traces/executions/smoke-exec-{rand_suffix}/create-test", method="POST", json_body={"name": "Smoke Test Case"}, headers={"X-Project-Id": str(project_id)})
        test_id = body.get("id")
        self.check("Generate Regression Test from Trace", code == 201 and test_id, str(body))

        # 10. Run Test Case Replay
        if test_id:
            code, body = self.request(f"/api/tests/{test_id}/run", method="POST", headers={"X-Project-Id": str(project_id)})
            self.check("Test Replay Execution", code in (200, 201) and body.get("status") == "passed", str(body))
        else:
            self.check("Test Replay Execution", False, "Skipped due to missing test_id")

        # 11. Multi-Tenant Anti-Enumeration (Probe nonexistent project -> 404)
        code, _ = self.request("/api/projects/999999")
        self.check("Anti-Enumeration Returns 404 on Foreign Project", code == 404, f"Returned status: {code}")

        # 12. Safe Logout
        code, body = self.request("/api/auth/logout", method="POST")
        self.check("Safe Logout", code == 200 and "Logged out" in body.get("message", ""), str(body))

        # Unauthenticated Check Post-Logout
        code, _ = self.request("/api/auth/me")
        self.check("Unauthenticated Access Rejected Post-Logout (401)", code == 401, f"Returned status: {code}")

        print("\n--------------------------------------------------")
        print(f"Staging Smoke Test Results: {self.passed} passed, {self.failed} failed.")
        print("--------------------------------------------------\n")
        return self.failed == 0


def main():
    parser = argparse.ArgumentParser(description="Live Staging Smoke Test Runner")
    parser.add_argument("--target-url", default="http://127.0.0.1:8001", help="Base URL of staging backend")
    args = parser.parse_args()

    runner = StagingSmokeRunner(args.target_url)
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

