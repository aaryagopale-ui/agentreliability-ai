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


def test_async_agent_success():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_agent("async_researcher")
    async def run(topic: str):
        await asyncio.sleep(0.01)
        return f"Report on {topic}"

    res = asyncio.run(run("reliability"))
    assert res == "Report on reliability"
    assert m.flush()

    assert len(c.events) == 2
    start = c.events[0]
    end = c.events[1]
    assert start["type"] == "execution_start"
    assert start["agent_name"] == "async_researcher"
    assert start["input"] == {"topic": "reliability"}
    assert end["type"] == "execution_end"
    assert end["status"] == "success"
    assert end["output"] == "Report on reliability"
    assert end["duration_ms"] > 0
    assert start["execution_id"] == end["execution_id"]


def test_async_tool_success():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_tool("async_fetch")
    async def fetch(url: str):
        await asyncio.sleep(0.01)
        return {"data": f"content from {url}"}

    @m.trace_agent("async_agent")
    async def run(url: str):
        data = await fetch(url)
        return data["data"]

    res = asyncio.run(run("https://api.example.com"))
    assert res == "content from https://api.example.com"
    assert m.flush()

    assert len(c.events) == 3
    tool_ev = c.events[1]
    assert tool_ev["type"] == "tool_call"
    assert tool_ev["tool_name"] == "async_fetch"
    assert tool_ev["status"] == "success"
    assert tool_ev["input"] == {"url": "https://api.example.com"}
    assert tool_ev["output"] == {"data": "content from https://api.example.com"}
    assert tool_ev["duration_ms"] > 0
    assert tool_ev["parent_call_id"] is None
    assert tool_ev["execution_id"] == c.events[0]["execution_id"]


def test_sync_tool_in_async_agent():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_tool("sync_calc")
    def calc(a: int, b: int):
        return a + b

    @m.trace_agent("async_calc_agent")
    async def run(a: int, b: int):
        await asyncio.sleep(0.005)
        return calc(a, b)

    res = asyncio.run(run(5, 7))
    assert res == 12
    assert m.flush()

    assert len(c.events) == 3
    tool_ev = c.events[1]
    assert tool_ev["type"] == "tool_call"
    assert tool_ev["tool_name"] == "sync_calc"
    assert tool_ev["status"] == "success"
    assert tool_ev["output"] == 12
    assert tool_ev["execution_id"] == c.events[0]["execution_id"]


def test_async_tool_in_sync_agent():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_tool("async_fetch")
    async def fetch(item_id: int):
        await asyncio.sleep(0.005)
        return f"item_{item_id}"

    @m.trace_agent("sync_agent_calling_async")
    def run(item_id: int):
        return asyncio.run(fetch(item_id))

    res = run(42)
    assert res == "item_42"
    assert m.flush()

    assert len(c.events) == 3
    tool_ev = c.events[1]
    assert tool_ev["type"] == "tool_call"
    assert tool_ev["tool_name"] == "async_fetch"
    assert tool_ev["status"] == "success"
    assert tool_ev["output"] == "item_42"


def test_async_agent_failure():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_agent("failing_async_agent")
    async def run():
        await asyncio.sleep(0.005)
        raise ValueError("async agent exploded")

    with pytest.raises(ValueError, match="async agent exploded"):
        asyncio.run(run())

    assert m.flush()
    assert len(c.events) == 2
    end = c.events[1]
    assert end["type"] == "execution_end"
    assert end["status"] == "failed"
    assert end["error_type"] == "ValueError"
    assert "async agent exploded" in end["error_message"]


def test_async_tool_failure_and_timeout():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_tool("failing_tool")
    async def fail_tool():
        await asyncio.sleep(0.005)
        raise ConnectionResetError("connection reset by peer")

    @m.trace_tool("timeout_tool")
    async def timeout_tool():
        await asyncio.sleep(0.005)
        raise TimeoutError("operation timed out after 5s")

    @m.trace_agent("agent_handling_errors")
    async def run(mode: str):
        if mode == "fail":
            try:
                await fail_tool()
            except ConnectionResetError:
                return "caught_fail"
        elif mode == "timeout":
            try:
                await timeout_tool()
            except TimeoutError:
                return "caught_timeout"

    res1 = asyncio.run(run("fail"))
    assert res1 == "caught_fail"
    res2 = asyncio.run(run("timeout"))
    assert res2 == "caught_timeout"
    assert m.flush()

    tools = by_type(c.events, "tool_call")
    assert len(tools) == 2
    assert tools[0]["tool_name"] == "failing_tool"
    assert tools[0]["status"] == "error"
    assert tools[0]["error_type"] == "ConnectionResetError"

    assert tools[1]["tool_name"] == "timeout_tool"
    assert tools[1]["status"] == "timeout"
    assert tools[1]["error_type"] == "TimeoutError"


def test_nested_async_tools():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_tool("child_tool")
    async def child_tool(val: int):
        await asyncio.sleep(0.005)
        return val * 2

    @m.trace_tool("parent_tool")
    async def parent_tool(val: int):
        res = await child_tool(val)
        return res + 1

    @m.trace_agent("nested_agent")
    async def run(val: int):
        return await parent_tool(val)

    assert asyncio.run(run(10)) == 21
    assert m.flush()

    tools = by_type(c.events, "tool_call")
    assert len(tools) == 2
    # In execution order, child finishes before parent
    child_ev = [t for t in tools if t["tool_name"] == "child_tool"][0]
    parent_ev = [t for t in tools if t["tool_name"] == "parent_tool"][0]

    assert child_ev["parent_call_id"] == parent_ev["event_id"]
    assert parent_ev["parent_call_id"] is None


def test_concurrent_async_tasks_isolated_context():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_tool("worker_tool")
    async def worker_tool(agent_id: str, step: int):
        await asyncio.sleep(0.01)
        return f"{agent_id}_step_{step}"

    @m.trace_agent("concurrent_worker")
    async def worker(agent_id: str):
        r1 = await worker_tool(agent_id, 1)
        r2 = await worker_tool(agent_id, 2)
        return [r1, r2]

    async def main():
        task1 = asyncio.create_task(worker("worker_A"))
        task2 = asyncio.create_task(worker("worker_B"))
        return await asyncio.gather(task1, task2)

    res = asyncio.run(main())
    assert res == [["worker_A_step_1", "worker_A_step_2"], ["worker_B_step_1", "worker_B_step_2"]]
    assert m.flush()

    starts = by_type(c.events, "execution_start")
    ends = by_type(c.events, "execution_end")
    tools = by_type(c.events, "tool_call")

    assert len(starts) == 2
    assert len(ends) == 2
    assert len(tools) == 4

    exec_ids = {s["execution_id"] for s in starts}
    assert len(exec_ids) == 2

    # Map each execution_id to its agent input
    exec_inputs = {s["execution_id"]: s["input"]["agent_id"] for s in starts}

    # Verify that every tool call belongs strictly to the execution where it was invoked
    for t in tools:
        assert t["execution_id"] in exec_ids
        expected_owner = exec_inputs[t["execution_id"]]
        assert t["input"]["agent_id"] == expected_owner
        assert expected_owner in t["output"]


def test_concurrent_async_tools_in_one_agent():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_tool("fast_tool")
    async def fast_tool(x: int):
        await asyncio.sleep(0.005)
        return x * 10

    @m.trace_agent("parallel_tools_agent")
    async def run():
        results = await asyncio.gather(fast_tool(1), fast_tool(2), fast_tool(3))
        return sum(results)

    assert asyncio.run(run()) == 60
    assert m.flush()

    tools = by_type(c.events, "tool_call")
    assert len(tools) == 3
    exec_id = c.events[0]["execution_id"]
    for t in tools:
        assert t["execution_id"] == exec_id
        assert t["parent_call_id"] is None
        assert t["status"] == "success"


def test_async_with_tool_call_context_manager():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_agent("ctx_agent")
    async def run():
        async with m.tool_call("manual_async_tool", input={"k": "v"}) as call:
            await asyncio.sleep(0.01)
            call.set_output({"res": 100})
            return 100

    assert asyncio.run(run()) == 100
    assert m.flush()

    tools = by_type(c.events, "tool_call")
    assert len(tools) == 1
    assert tools[0]["tool_name"] == "manual_async_tool"
    assert tools[0]["output"] == {"res": 100}


def test_disabled_async_agent():
    import asyncio
    m, c = make(enabled=False)

    @m.trace_tool("tool")
    async def a_tool():
        return 99

    @m.trace_agent("a")
    async def run():
        return await a_tool()

    assert asyncio.run(run()) == 99
    assert m.flush() and c.events == []


def test_async_generators_still_warn():
    import warnings
    m, c = make()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @m.trace_agent("gen_agent")
        async def gen():
            yield 1

    assert any("async generator" in str(x.message) for x in w)


def test_disabled_monitor_sends_nothing():
    m, c = make(enabled=False)

    @m.trace_agent("a")
    def run():
        return 3

    assert run() == 3
    assert m.flush() and c.events == []


def test_nested_tool_calls_and_retries_tracking():
    m, c = make(capture_io=True)

    @m.trace_tool("child_tool")
    def child_tool(val: int):
        return val * 2

    @m.trace_tool("parent_tool", retry_count=1)
    def parent_tool(x: int):
        return child_tool(x) + 1

    @m.trace_agent("test_agent")
    def run_agent():
        return parent_tool(5)

    assert run_agent() == 11
    m.flush()

    tool_events = [e for e in c.events if e["type"] == "tool_call"]
    assert len(tool_events) == 2

    # child tool completes first, then parent tool completes
    child_event = next(e for e in tool_events if e["tool_name"] == "child_tool")
    parent_event = next(e for e in tool_events if e["tool_name"] == "parent_tool")

    assert parent_event["retry_count"] == 1
    assert parent_event["parent_call_id"] is None
    assert child_event["parent_call_id"] == parent_event["event_id"]
    assert child_event["retry_count"] == 0


def test_package_level_convenience_exports(monkeypatch):
    import agentreliability
    # Ensure default monitor works
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_live_mocktestkey1234567890123456")
    monkeypatch.setenv("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")
    agentreliability._default_monitor = None

    @agentreliability.trace_tool("test_convenience_tool")
    def helper_tool(n: int):
        return n + 10

    @agentreliability.trace_agent("convenience_agent")
    def agent_main():
        return helper_tool(5)

    assert agent_main() == 15
    assert agentreliability.flush() is True


# ---------------------------------------------------------------- trace_execution (Issue #3)

def test_trace_execution_sync_success():
    m, c = make(capture_io=True, metadata={"env": "unit_test"})

    with m.trace_execution("data_processor", input_data={"batch_id": 101}) as trace:
        assert trace.execution_id
        assert trace.name == "data_processor"
        time.sleep(0.01)
        trace.set_output({"processed_rows": 50, "status": "ok"})

    assert m.flush()
    assert len(c.events) == 2
    start, end = c.events[0], c.events[1]

    assert start["type"] == "execution_start"
    assert start["agent_name"] == "data_processor"
    assert start["execution_id"] == trace.execution_id
    assert start["input"] == {"batch_id": 101}
    assert start["metadata"] == {"env": "unit_test"}

    assert end["type"] == "execution_end"
    assert end["execution_id"] == trace.execution_id
    assert end["status"] == "success"
    assert end["output"] == {"processed_rows": 50, "status": "ok"}
    assert end["duration_ms"] > 0
    assert trace.duration_ms > 0


def test_trace_execution_set_input_dynamic():
    m, c = make(capture_io=True)

    with m.trace_execution("dynamic_flow") as trace:
        # Input wasn't known at enter time, set inside block
        trace.set_input({"customer_id": "CUST-999"})
        trace.set_output("success")

    assert m.flush()
    start_events = [e for e in c.events if e["type"] == "execution_start"]
    assert len(start_events) >= 1
    # Check that latest start event has the dynamic input
    assert start_events[-1]["input"] == {"customer_id": "CUST-999"}


def test_trace_execution_sync_exception_reraised():
    m, c = make(capture_io=True)

    with pytest.raises(ZeroDivisionError, match="division by zero"):
        with m.trace_execution("math_block", input_data={"divisor": 0}) as trace:
            _ = 100 / 0

    assert m.flush()
    assert len(c.events) == 2
    end = c.events[1]
    assert end["type"] == "execution_end"
    assert end["status"] == "failed"
    assert end["error_type"] == "ZeroDivisionError"
    assert "division by zero" in end["error_message"]


def test_trace_execution_explicit_set_error():
    m, c = make(capture_io=True)

    with m.trace_execution("payment_service") as trace:
        trace.set_output({"attempted": True})
        trace.set_error("Payment gateway connection rejected")

    assert m.flush()
    assert len(c.events) == 2
    end = c.events[1]
    assert end["status"] == "failed"
    assert end["error_type"] == "ExecutionError"
    assert end["error_message"] == "Payment gateway connection rejected"
    assert end["output"] == {"attempted": True}


def test_trace_execution_explicit_set_error_exception_object():
    m, c = make(capture_io=True)

    with m.trace_execution("custom_service") as trace:
        trace.set_error(ValueError("Invalid state transition"))

    assert m.flush()
    end = c.events[1]
    assert end["status"] == "failed"
    assert end["error_type"] == "ValueError"
    assert end["error_message"] == "Invalid state transition"


def test_trace_execution_nested_tool_calls():
    m, c = make(capture_io=True)

    @m.trace_tool("fetch_data")
    def fetch_data(key: str):
        return f"value_{key}"

    with m.trace_execution("parent_pipeline", input_data={"key": "k1"}) as trace:
        val = fetch_data("k1")
        with m.tool_call("save_data", input=val) as t:
            t.set_output("saved")
        trace.set_output("done")

    assert m.flush()
    tool_events = [e for e in c.events if e["type"] == "tool_call"]
    assert len(tool_events) == 2
    for t_ev in tool_events:
        assert t_ev["execution_id"] == trace.execution_id
        assert t_ev["agent_name"] == "parent_pipeline"
        assert t_ev["status"] == "success"


def test_trace_execution_async_success():
    import asyncio
    m, c = make(capture_io=True)

    async def run_async_task():
        async with m.trace_execution("async_pipeline", input_data={"items": 3}) as trace:
            await asyncio.sleep(0.01)
            trace.set_output({"items": 3, "status": "completed"})
            return trace.execution_id

    exec_id = asyncio.run(run_async_task())
    assert m.flush()
    assert len(c.events) == 2
    end = c.events[1]
    assert end["execution_id"] == exec_id
    assert end["status"] == "success"
    assert end["output"] == {"items": 3, "status": "completed"}
    assert end["duration_ms"] > 0


def test_trace_execution_async_exception_reraised():
    import asyncio
    m, c = make(capture_io=True)

    async def run_failing_task():
        async with m.trace_execution("failing_async", input_data={"run": True}) as trace:
            await asyncio.sleep(0.01)
            raise KeyError("missing_config_key")

    with pytest.raises(KeyError, match="missing_config_key"):
        asyncio.run(run_failing_task())

    assert m.flush()
    assert len(c.events) == 2
    end = c.events[1]
    assert end["status"] == "failed"
    assert end["error_type"] == "KeyError"
    assert "missing_config_key" in end["error_message"]


def test_trace_execution_concurrent_isolation():
    import asyncio
    m, c = make(capture_io=True)

    @m.trace_tool("concurrent_tool")
    async def sub_tool(worker_id: str):
        await asyncio.sleep(0.01)
        return f"result_{worker_id}"

    async def worker(worker_id: str):
        async with m.trace_execution(f"worker_{worker_id}", input_data={"worker_id": worker_id}) as trace:
            await sub_tool(worker_id)
            trace.set_output(f"done_{worker_id}")
            return trace.execution_id

    async def main():
        return await asyncio.gather(worker("A"), worker("B"))

    id_a, id_b = asyncio.run(main())
    assert id_a != id_b
    assert m.flush()

    tools = [e for e in c.events if e["type"] == "tool_call"]
    assert len(tools) == 2

    tool_a = next(t for t in tools if t["input"] == {"worker_id": "A"})
    tool_b = next(t for t in tools if t["input"] == {"worker_id": "B"})

    assert tool_a["execution_id"] == id_a
    assert tool_a["agent_name"] == "worker_A"
    assert tool_b["execution_id"] == id_b
    assert tool_b["agent_name"] == "worker_B"


def test_trace_execution_disabled_monitoring(caplog):
    m = AgentMonitor(endpoint="http://x.test")  # No API key -> disabled
    assert m.enabled is False

    with m.trace_execution("disabled_task", input_data={"key": "val"}) as trace:
        assert trace.execution_id == ""
        trace.set_input({"updated": True})
        trace.set_output({"res": 1})
        trace.set_error("Ignored error")

    # Verify exception inside disabled block is still re-raised properly
    with pytest.raises(ValueError, match="boom"):
        with m.trace_execution("disabled_task_fail"):
            raise ValueError("boom")


def test_trace_execution_top_level_package_convenience(monkeypatch):
    import agentreliability
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "ar_live_mocktestkey1234567890123456")
    monkeypatch.setenv("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:8001")
    agentreliability._default_monitor = None

    with agentreliability.trace_execution("pkg_level_task", input_data={"a": 1}) as trace:
        assert trace.execution_id
        trace.set_output({"result": "success"})

    assert agentreliability.flush() is True


# ---------------------------------------------------------------- package-level tool_call (Issue #6)

def test_package_level_tool_call_export():
    import agentreliability
    assert hasattr(agentreliability, "tool_call")
    assert callable(agentreliability.tool_call)
    assert "tool_call" in agentreliability.__all__


def test_package_level_tool_call_sync_success(monkeypatch):
    import agentreliability
    c = Collector()
    agentreliability.init(
        endpoint="http://example.test",
        api_key=KEY,
        _post=c,
        capture_io=True,
        retry_backoff=0.0,
    )

    with agentreliability.trace_execution("tax_service", input_data={"subtotal": 100}) as trace:
        with agentreliability.tool_call("calc_tax", input={"rate": 0.1, "amount": 100}) as t:
            t.set_output({"tax": 10})
        trace.set_output({"total": 110})

    assert agentreliability.flush() is True
    tool_events = [e for e in c.events if e["type"] == "tool_call"]
    assert len(tool_events) == 1
    t_ev = tool_events[0]
    assert t_ev["tool_name"] == "calc_tax"
    assert t_ev["status"] == "success"
    assert t_ev["input"] == {"rate": 0.1, "amount": 100}
    assert t_ev["output"] == {"tax": 10}
    assert t_ev["execution_id"] == trace.execution_id
    assert t_ev["agent_name"] == "tax_service"


def test_package_level_tool_call_nested_hierarchy(monkeypatch):
    import agentreliability
    c = Collector()
    agentreliability.init(
        endpoint="http://example.test",
        api_key=KEY,
        _post=c,
        capture_io=True,
        retry_backoff=0.0,
    )

    with agentreliability.trace_execution("order_pipeline", input_data={"id": "O-1"}) as trace:
        with agentreliability.tool_call("parent_step", input={"step": 1}) as t_parent:
            with agentreliability.tool_call("child_substep", input={"substep": "1a"}) as t_child:
                t_child.set_output("substep_complete")
            t_parent.set_output("step_complete")
        trace.set_output("order_complete")

    assert agentreliability.flush() is True
    tool_events = [e for e in c.events if e["type"] == "tool_call"]
    assert len(tool_events) == 2

    child_ev = next(e for e in tool_events if e["tool_name"] == "child_substep")
    parent_ev = next(e for e in tool_events if e["tool_name"] == "parent_step")

    assert parent_ev["parent_call_id"] is None
    assert child_ev["parent_call_id"] == parent_ev["event_id"]
    assert parent_ev["execution_id"] == trace.execution_id
    assert child_ev["execution_id"] == trace.execution_id


def test_package_level_tool_call_async_usage(monkeypatch):
    import asyncio
    import agentreliability
    c = Collector()
    agentreliability.init(
        endpoint="http://example.test",
        api_key=KEY,
        _post=c,
        capture_io=True,
        retry_backoff=0.0,
    )

    async def run_async_flow():
        async with agentreliability.trace_execution("async_search", input_data={"q": "rag"}) as trace:
            async with agentreliability.tool_call("vector_lookup", input={"q": "rag"}) as t:
                await asyncio.sleep(0.01)
                t.set_output({"matches": 5})
            trace.set_output("done")
            return trace.execution_id

    exec_id = asyncio.run(run_async_flow())
    assert agentreliability.flush() is True

    tool_events = [e for e in c.events if e["type"] == "tool_call"]
    assert len(tool_events) == 1
    t_ev = tool_events[0]
    assert t_ev["tool_name"] == "vector_lookup"
    assert t_ev["status"] == "success"
    assert t_ev["output"] == {"matches": 5}
    assert t_ev["execution_id"] == exec_id


def test_package_level_tool_call_disabled_monitoring(monkeypatch):
    import agentreliability
    # Reconfigure default monitor without an API key
    monkeypatch.delenv("AGENTRELIABILITY_API_KEY", raising=False)
    agentreliability._default_monitor = None
    agentreliability.init(endpoint="http://x.test", api_key=None)
    assert agentreliability.get_default_monitor().enabled is False

    # Calling tool_call when disabled does not raise exceptions
    with agentreliability.tool_call("noop_tool", input={"x": 1}) as t:
        t.set_input({"x": 2})
        t.set_output({"res": 3})

    # But exceptions inside the block are still re-raised properly
    with pytest.raises(RuntimeError, match="critical error in user code"):
        with agentreliability.tool_call("failing_tool"):
            raise RuntimeError("critical error in user code")


def test_package_level_tool_call_outside_execution_is_safe(monkeypatch):
    import agentreliability
    c = Collector()
    agentreliability.init(endpoint="http://example.test", api_key=KEY, _post=c)

    # Calling tool_call outside of any active trace_agent / trace_execution
    with agentreliability.tool_call("standalone_tool", input="data") as t:
        t.set_output("result")

    # Emits nothing because there is no parent execution, but does not crash
    assert agentreliability.flush() is True
    tool_events = [e for e in c.events if e["type"] == "tool_call"]
    assert len(tool_events) == 0


def test_package_level_tool_call_input_data_alias(monkeypatch):
    import agentreliability
    c = Collector()
    agentreliability.init(
        endpoint="http://example.test",
        api_key=KEY,
        _post=c,
        capture_io=True,
        retry_backoff=0.0,
    )

    with agentreliability.trace_execution("alias_task") as trace:
        with agentreliability.tool_call("aliased_tool", input_data={"param": 42}) as t:
            t.set_output("ok")

    assert agentreliability.flush() is True
    tool_events = [e for e in c.events if e["type"] == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["input"] == {"param": 42}



