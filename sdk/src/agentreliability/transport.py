"""Background sender. The agent thread only does `queue.put_nowait`; all network work happens
on a separate daemon thread, and every failure is swallowed, so monitoring can never break
(or slow down) the developer's code."""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

log = logging.getLogger("agentreliability")

BATCH_SIZE = 50

PostFunc = Callable[[str, dict, bytes, float], int]


def default_post(url: str, headers: dict, body: bytes, timeout: float) -> int:
    """POST using only the standard library. Returns the HTTP status code."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked by caller)
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


class Transport:
    def __init__(self, endpoint: str, api_key: str, timeout: float = 2.0, max_queue: int = 1000,
                 retries: int = 2, retry_backoff: float = 0.25, post: Optional[PostFunc] = None):
        self._url = endpoint.rstrip("/") + "/api/v1/traces/events"
        self._headers = {"Content-Type": "application/json", "X-API-Key": api_key}
        self._timeout = timeout
        self._retries = retries
        self._backoff = retry_backoff
        self._post = post or default_post
        self._queue: "queue.Queue[dict]" = queue.Queue(maxsize=max_queue)
        self._pending = 0
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.dropped = 0
        self.failed_batches = 0
        self._warned = False

    def __repr__(self) -> str:  # never include the key
        return f"Transport(url={self._url!r})"

    # -- called from the developer's thread --------------------------------------------
    def submit(self, event: dict) -> None:
        with self._lock:
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                self.dropped += 1
                return
            self._pending += 1
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="agentreliability-sender", daemon=True)
                self._thread.start()

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until queued events were sent (or given up on). Returns True if nothing is pending."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._pending == 0:
                    return True
            time.sleep(0.01)
        return False

    # -- background thread ------------------------------------------------------------
    def _run(self) -> None:
        while True:
            try:
                first = self._queue.get(timeout=1.0)
            except queue.Empty:
                # Decide to exit under the lock: submit() either sees our event in the queue
                # (we keep going) or sees _thread is None and starts a new thread.
                with self._lock:
                    if self._queue.empty():
                        self._thread = None
                        return
                continue
            batch = [first]
            while len(batch) < BATCH_SIZE:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                self._send(batch)
            except Exception:  # absolutely nothing may escape this thread
                log.debug("agentreliability: unexpected sender error", exc_info=True)
            finally:
                with self._lock:
                    self._pending -= len(batch)

    def _send(self, batch: list) -> None:
        body = json.dumps({"events": batch}).encode("utf-8")
        for attempt in range(self._retries + 1):
            try:
                status = self._post(self._url, self._headers, body, self._timeout)
            except Exception as exc:  # connection refused, timeout, DNS ... -> retry
                log.debug("agentreliability: send failed (%s)", type(exc).__name__)
            else:
                if 200 <= status < 300:
                    return
                if status < 500 and status != 429:
                    self._warn(f"backend rejected the traces (HTTP {status}); check your API key and endpoint")
                    self.failed_batches += 1
                    return  # retrying a 4xx would never help
            if attempt < self._retries:
                time.sleep(self._backoff * (attempt + 1))
        self.failed_batches += 1
        self._warn("could not reach the backend; traces were dropped (your agent is unaffected)")

    def _warn(self, message: str) -> None:
        if not self._warned:  # warn once, never include secrets
            self._warned = True
            log.warning("agentreliability: %s", message)
