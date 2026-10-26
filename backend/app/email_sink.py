"""In-memory local development and test email sink.

Security Guarantees:
1. In production (AGENTRELIABILITY_ENV=production):
   - Fails closed: will NEVER store or capture reset tokens.
   - Raw tokens are NEVER logged or exposed.
2. In development and automated tests:
   - Captures simulated password reset email delivery in memory for automated testing.
   - Can be inspected by tests without printing tokens into production logs.
"""
from __future__ import annotations

import os
from typing import Dict, Optional


def is_production() -> bool:
    env = os.environ.get("AGENTRELIABILITY_ENV", "development").strip().lower()
    return env == "production"


class DevEmailSink:
    """Thread-safe development sink for testing password reset delivery."""

    def __init__(self):
        self._sent_resets: Dict[str, str] = {}

    def deliver_reset_token(self, email: str, token: str) -> bool:
        """Deliver token to local development sink. Fails closed in production."""
        if is_production():
            return False  # Strict fail-closed: never capture in production
        self._sent_resets[email.lower().strip()] = token
        return True

    def get_latest_token(self, email: str) -> Optional[str]:
        if is_production():
            return None  # Never retrieve in production
        return self._sent_resets.get(email.lower().strip())

    def clear(self) -> None:
        self._sent_resets.clear()


dev_email_sink = DevEmailSink()

