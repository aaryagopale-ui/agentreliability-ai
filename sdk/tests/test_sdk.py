import logging
import time
import warnings

import pytest

from agentreliability import AgentMonitor

KEY = "ar_test_key_0123456789abcdefghij"


class Collector:
    """Fake network: remembers every event the SDK tries to send."""

    def __init__(self, status=200):
        self.events, self.status, self.calls = [], status, []

    def __call__(self, url, headers, body, timeout):
        import json
        self.calls.append((url, headers))
        self.events.extend(json.loads(body)["events"])
        return self.status


def make(collector=None, **kw):
    collector = collector or Collector()
    kw.setdefault("retry_backoff", 0.0)
    m = AgentMonitor(endpoint="http://example.test", api_key=KEY, _post=collector, **kw)
    return m, collector


def by_type(events, t):
    return [e for e in events if e["type"] == t]


# ---------------------------------------------------------------- imports / config

def test_import_and_version():
    import agentreliability
    assert agentreliability.__version__ == "0.1.0"
    assert agentreliability.AgentMonitor is AgentMonitor


def test_no_api_key_disables_monitoring_but_function_still_works(monkeypatch, caplog):
    monkeypatch.delenv("AGENTRELIABILITY_API_KEY", raising=False)
    with caplog.at_level(logging.WARNING, logger="agentreliability"):
        m = AgentMonitor(endpoint="http://x.test")

    @m.trace_agent("a")
    def f(x):
        return x * 2

    assert m.enabled is False and f(4) == 8
    assert "disabled" in caplog.text


def test_api_key_and_endpoint_from_environment(monkeypatch):
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", KEY)
    monkeypatch.setenv("AGENTRELIABILITY_ENDPOINT", "http://env.test:9000/")
    m = AgentMonitor()
    assert m.enabled and m.endpoint == "http://env.test:9000"


def test_bad_endpoint_scheme_is_refused():
    m = AgentMonitor(endpoint="file:///etc/passwd", api_key=KEY)
    assert m.enabled is False


def test_key_never_in_repr_or_logs(caplog):
    caplog.set_level(logging.DEBUG, logger="agentreliability")
    m, c = make()
    assert KEY not in repr(m) and KEY not in repr(m._transport)

    @m.trace_agent("a")
    def f():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        f()
    m.flush()
    assert KEY not in caplog.text
    assert c.calls[0][1]["X-API-Key"] == KEY  # it IS sent as a header, only there


# ---------------------------------------------------------------- decorator behaviour

def test_decorator_preserves_behavior_and_metadata():
    m, _ = make()

    @m.trace_agent("agent")
    def add(a, b=10, *rest, **kw):
        """Adds."""
        return a + b + sum(rest) + sum(kw.values())

    assert add(1) == 11
    assert add(1, 2, 3, z=4) == 10
    assert add.__name__ == "add" and add.__doc__ == "Adds."


def test_successful_execution_events():
    m, c = make(metadata={"env": "test"})

    @m.trace_agent("research-agent", metadata={"version": "1.2"})
    def run(question):
        return "answer"

    assert run("why?") == "answer"
    assert m.flush()
    start, end = by_type(c.events, "execution_start")[0], by_type(c.events, "execution_end")[0]
    assert start["agent_name"] == "research-agent"
    assert start["execution_id"] == end["execution_id"]
    assert start["event_id"] == f"{start['execution_id']}:start"
    assert end["event_id"] == f"{start['execution_id']}:end"
    assert end["status"] == "success" and end["duration_ms"] >= 0
    assert start["metadata"] == {"env": "test", "version": "1.2"}
    assert start["timestamp"].endswith("+00:00") and end["timestamp"].endswith("+00:00")  # UTC


def test_each_call_gets_unique_execution_id():
    m, c = make()

    @m.trace_agent("a")
    def f():
        return 1

    f(); f(); f()
    m.flush()
    ids = {e["execution_id"] for e in c.events}
    assert len(ids) == 3


def test_duration_is_measured():
    m, c = make()

    @m.trace_agent("a")
    def slow():
        time.sleep(0.05)

    slow()
    m.flush()
    assert by_type(c.events, "execution_end")[0]["duration_ms"] >= 45


def test_exception_propagates_unchanged_and_is_recorded():
    m, c = make()
    boom = ValueError("bad thing")

    @m.trace_agent("a")
    def f():
        raise boom

    with pytest.raises(ValueError) as info:
        f()
    assert info.value is boom  # the SAME object
    m.flush()
    end = by_type(c.events, "execution_end")[0]
    assert end["status"] == "failed" and end["error_type"] == "ValueError" and end["error_message"] == "bad thing"


def test_timeout_error_in_tool_is_labelled_timeout():
    m, c = make()

    @m.trace_agent("a")
    def f():
        with m.tool_call("slow_api"):
            raise TimeoutError("took too long")

    with pytest.raises(TimeoutError):
        f()
    m.flush()
    tool = by_type(c.events, "tool_call")[0]
    assert tool["status"] == "timeout" and tool["tool_name"] == "slow_api"


# ---------------------------------------------------------------- tool calls

def test_tool_calls_traced_in_order_with_stable_ids():
    m, c = make(capture_io=True)

    @m.trace_tool("search")
    def search(q):
        return ["r1"]

    @m.trace_agent("a")
    def run():
        search("x")
        with m.tool_call("manual", input={"k": 1}) as call:
            call.set_output("done")
        return "ok"

    run()
    m.flush()
    tools = by_type(c.events, "tool_call")
    assert [t["tool_name"] for t in tools] == ["search", "manual"]
    assert tools[0]["event_id"].endswith(":tool:1") and tools[1]["event_id"].endswith(":tool:2")
    assert tools[0]["input"] == {"q": "x"} and tools[0]["output"] == ["r1"]
    assert tools[1]["output"] == "done" and tools[0]["status"] == "success"


def test_failed_tool_records_error_and_reraises():
    m, c = make()

    @m.trace_tool()
    def flaky():
        raise ConnectionError("503")

    @m.trace_agent("a")
    def run():
        flaky()

    with pytest.raises(ConnectionError):
        run()
    m.flush()
    tool = by_type(c.events, "tool_call")[0]
    assert tool["tool_name"] == "flaky" and tool["status"] == "error" and tool["error_type"] == "ConnectionError"


def test_tool_outside_agent_trace_just_runs():
    m, c = make()

    @m.trace_tool("t")
    def t():
        return 5

    assert t() == 5
    m.flush()
    assert c.events == []


# ---------------------------------------------------------------- privacy

def test_io_not_captured_by_default():
    m, c = make()

    @m.trace_agent("a")
    def run(question):
        return "secret answer"

    run("private question")
    m.flush()
    start, end = by_type(c.events, "execution_start")[0], by_type(c.events, "execution_end")[0]
    assert start["input"] is None and end["output"] is None
    assert "private question" not in str(c.events) and "secret answer" not in str(c.events)


def test_capture_io_with_redaction():
    m, c = make(capture_io=True)

    @m.trace_agent("a")
    def run(question, password, config):
        return {"reply": "contact bob@example.com", "token": "abc"}

    run("hi", "hunter2", {"api_key": "zzz", "note": "uses sk-abcdefghijklmnop1234"})
    m.flush()
    dumped = str(c.events)
    for leaked in ("hunter2", "zzz", "bob@example.com", "sk-abcdefghijklmnop1234", "'abc'"):
        assert leaked not in dumped
    start = by_type(c.events, "execution_start")[0]
    assert start["input"]["question"] == "hi" and start["input"]["password"] == "[REDACTED]"


def test_custom_redaction_keys_and_patterns():
    m, c = make(capture_io=True, redact_keys=["ssn"], redact_patterns=[r"ORDER-\d+"])

    @m.trace_agent("a")
    def run(data):
        return "see ORDER-12345"

    run({"ssn": "123-45-6789", "ok": 1})
    m.flush()
    dumped = str(c.events)
    assert "123-45-6789" not in dumped and "ORDER-12345" not in dumped


def test_error_messages_are_redacted():
    m, c = make()

    @m.trace_agent("a")
    def run():
        raise RuntimeError("auth failed with Bearer abc.def.ghi for user@corp.com")

    with pytest.raises(RuntimeError):
        run()
    m.flush()
    msg = by_type(c.events, "execution_end")[0]["error_message"]
    assert "abc.def.ghi" not in msg and "user@corp.com" not in msg


def test_payload_is_size_limited():
    m, c = make(capture_io=True, max_payload_chars=300)

    @m.trace_agent("a")
    def run(blob):
        return "x" * 100_000

    run("y" * 100_000)
    m.flush()
    for e in c.events:
        for field in ("input", "output"):
            if e.get(field) is not None:
                assert len(str(e[field])) < 600


def test_metadata_sensitive_keys_redacted():
    m, c = make(metadata={"api_key": "shh", "team": "core"})

    @m.trace_agent("a")
    def run():
        pass

    run()
    m.flush()
    meta = by_type(c.events, "execution_start")[0]["metadata"]
    assert meta == {"api_key": "[REDACTED]", "team": "core"}


# ---------------------------------------------------------------- reliability

def test_backend_unreachable_never_breaks_the_agent():
    # Port 1 refuses connections. Uses the real urllib transport.
    m = AgentMonitor(endpoint="http://127.0.0.1:1", api_key=KEY, retries=1, retry_backoff=0.0, timeout=0.5)

    @m.trace_agent("a")
    def run(x):
        return x + 1

    started = time.perf_counter()
    assert run(1) == 2
    assert time.perf_counter() - started < 0.5  # agent is not slowed by the network
    m.flush(timeout=5)
    assert m._transport.failed_batches >= 1  # start/end events may travel in 1 or 2 batches


def test_backend_unreachable_exceptions_still_propagate():
    m = AgentMonitor(endpoint="http://127.0.0.1:1", api_key=KEY, retries=0, timeout=0.5)

    @m.trace_agent("a")
    def run():
        raise KeyError("k")

    with pytest.raises(KeyError):
        run()
    m.flush(timeout=3)


def test_transport_exception_is_swallowed():
    def exploding_post(*a):
        raise OSError("network down")

    m = AgentMonitor(endpoint="http://x.test", api_key=KEY, _post=exploding_post, retries=1, retry_backoff=0.0)

    @m.trace_agent("a")
    def run():
        return "fine"

    assert run() == "fine"
    assert m.flush(timeout=3)


def test_http_401_is_not_retried_and_does_not_break():
    c = Collector(status=401)
    m, _ = make(c, retries=3)

    @m.trace_agent("a")
    def run():
        return 1

    assert run() == 1
    m.flush()
    # No retries: each of the 2 events (start, end) was sent exactly once, in 1 or 2 batches.
    ids = [e["event_id"] for e in c.events]
    assert len(ids) == len(set(ids)) == 2


def test_unrepresentable_objects_do_not_break_capture():
    class Evil:
        def __repr__(self):
            raise RuntimeError("repr exploded")

    m, c = make(capture_io=True)

    @m.trace_agent("a")
    def run(obj):
        return Evil()

    assert isinstance(run(Evil()), Evil)
    m.flush()
    assert by_type(c.events, "execution_end")[0]["status"] == "success"


def test_queue_overflow_drops_instead_of_blocking():
    gate = []

    def slow_post(url, headers, body, timeout):
        while not gate:
            time.sleep(0.01)
        return 200

    m = AgentMonitor(endpoint="http://x.test", api_key=KEY, _post=slow_post, max_queue=3)

    @m.trace_agent("a")
    def run():
        return 1

    for _ in range(10):
        run()
    assert m.dropped_events > 0
    gate.append(1)
    m.flush(timeout=5)


def test_async_functions_warn_and_run_untraced():
    import asyncio
    m, c = make()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @m.trace_agent("a")
        async def run():
            return 7

    assert any("async" in str(x.message) for x in w)
    assert asyncio.run(run()) == 7
    m.flush()
    assert c.events == []


def test_disabled_monitor_sends_nothing():
    m, c = make(enabled=False)

    @m.trace_agent("a")
    def run():
        return 3

    assert run() == 3
    assert m.flush() and c.events == []
