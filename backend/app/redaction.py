"""Backend secret redaction and payload sanitization.

Ensures that before trace data or error strings are processed, logged,
or sent to local AI models, all secrets and sensitive identifiers are redacted.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable, Optional, Union

log = logging.getLogger("agentreliability.redaction")

REDACTED = "[REDACTED]"

# A key is sensitive if its lowercase name CONTAINS one of these pieces.
DEFAULT_SENSITIVE_KEYS = (
    "password", "passwd", "secret", "token", "api_key", "apikey", "api-key",
    "authorization", "cookie", "credential", "private_key", "access_key", "session",
    "x-api-key", "csrf", "bearer", "secret_key", "client_secret",
)

DEFAULT_PATTERNS = (
    r"\bsk-[A-Za-z0-9_\-]{16,}",                       # OpenAI-style keys
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]+=*",           # Authorization headers
    r"\bar_[A-Za-z0-9_\-]{20,}",                       # AgentReliability keys
    r"\bAKIA[0-9A-Z]{16}\b",                           # AWS access key ids
    r"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,24}",  # emails
)

MAX_DEPTH = 6
MAX_ITEMS = 50
MAX_SCAN_CHARS = 20_000


class Redactor:
    def __init__(self, extra_keys: Iterable[str] = (), extra_patterns: Iterable[Union[str, re.Pattern]] = ()):
        self.keys = tuple(k.lower() for k in DEFAULT_SENSITIVE_KEYS) + tuple(str(k).lower() for k in extra_keys)
        self.patterns = []
        for p in tuple(DEFAULT_PATTERNS) + tuple(extra_patterns):
            try:
                self.patterns.append(re.compile(p) if isinstance(p, str) else p)
            except re.error:
                log.warning("agentreliability: ignoring an invalid redaction pattern")

    def is_sensitive_key(self, key: Any) -> bool:
        k = str(key).lower()
        return any(piece in k for piece in self.keys)

    def redact_text(self, text: str) -> str:
        if not text:
            return ""
        if len(text) > MAX_SCAN_CHARS:
            text = text[:MAX_SCAN_CHARS]
        for pattern in self.patterns:
            text = pattern.sub(REDACTED, text)
        return text

    def _walk(self, value: Any, depth: int) -> Any:
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            return value if value == value and value not in (float("inf"), float("-inf")) else str(value)
        if isinstance(value, str):
            return self.redact_text(value)
        if depth >= MAX_DEPTH:
            return "[max depth]"
        if isinstance(value, dict):
            out = {}
            for i, (k, v) in enumerate(value.items()):
                if i >= MAX_ITEMS:
                    out["..."] = f"{len(value) - MAX_ITEMS} more items"
                    break
                out[str(k)] = REDACTED if self.is_sensitive_key(k) else self._walk(v, depth + 1)
            return out
        if isinstance(value, (list, tuple, set, frozenset)):
            items = list(value)
            out = [self._walk(v, depth + 1) for v in items[:MAX_ITEMS]]
            if len(items) > MAX_ITEMS:
                out.append(f"... {len(items) - MAX_ITEMS} more items")
            return out
        try:
            text = repr(value)
        except Exception:
            text = f"<unrepresentable {type(value).__name__}>"
        return self.redact_text(text)

    def sanitize(self, value: Any, max_chars: int = 5000) -> Any:
        """Redact sensitive keys/patterns and ensure data is strictly JSON-serializable."""
        safe = self._walk(value, 0)
        try:
            dumped = json.dumps(safe)
        except (TypeError, ValueError):
            dumped = json.dumps(str(safe))
            safe = str(safe)
        if len(dumped) > max_chars:
            return {"_truncated": True, "preview": dumped[:max_chars]}
        return safe

    def sanitize_text(self, text: Optional[str], max_chars: int = 2000) -> Optional[str]:
        if text is None:
            return None
        return self.redact_text(text)[:max_chars]


# Global singleton instance
global_redactor = Redactor()

