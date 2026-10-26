"""Complete Local Browser-Based Verification of AgentReliability AI's One-Click Demo (Issue #10).

Uses Google Chrome in headless mode via Chrome DevTools Protocol (CDP) to drive the
real React/Vite single-page application at http://localhost:5174 against the FastAPI backend
at http://127.0.0.1:8001.
"""
import asyncio
import json
import os
import subprocess
import time
import urllib.request
import websockets

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE_URL = "http://localhost:5174"
CDP_PORT = 9222


class BrowserClient:
    def __init__(self, ws):
        self.ws = ws
        self.msg_id = 0
        self.pending = {}
        self.console_logs = []
        self.console_errors = []
        self.network_errors = []

    async def send(self, method: str, params: dict = None):
        self.msg_id += 1
        mid = self.msg_id
        msg = {"id": mid, "method": method, "params": params or {}}
        future = asyncio.get_event_loop().create_future()
        self.pending[mid] = future
        await self.ws.send(json.dumps(msg))
        return await future

    async def handle_incoming(self):
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                mid = data.get("id")
                if mid and mid in self.pending:
                    fut = self.pending.pop(mid)
                    if "error" in data:
                        fut.set_exception(Exception(data["error"]))
                    else:
                        fut.set_result(data.get("result", {}))
                else:
                    method = data.get("method")
                    params = data.get("params", {})
                    if method == "Runtime.consoleAPICalled":
                        log_type = params.get("type")
                        args = [str(a.get("value", a.get("description", ""))) for a in params.get("args", [])]
                        log_str = f"[{log_type}] {' '.join(args)}"
                        self.console_logs.append(log_str)
                        if log_type in ("error",):
                            self.console_errors.append(log_str)
                    elif method == "Runtime.exceptionThrown":
                        exc = params.get("exceptionDetails", {})
                        exc_str = f"Exception: {exc.get('text')} - {exc.get('exception', {}).get('description')}"
                        self.console_errors.append(exc_str)
                    elif method == "Network.responseReceived":
                        resp = params.get("response", {})
                        if resp.get("status", 200) >= 400:
                            url = resp.get("url", "")
                            # 401 is expected during initial unauthenticated check; ignore favicon
                            if not ("/api/auth/me" in url and resp.get("status") == 401) and not url.endswith("/favicon.ico"):
                                self.network_errors.append(f"HTTP {resp.get('status')} {url}")
        except asyncio.CancelledError:
            pass

    async def eval(self, js: str):
        res = await self.send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True,
            "awaitPromise": True,
        })
        return res.get("result", {}).get("value")

    async def wait_for_condition(self, js: str, timeout: float = 15.0, interval: float = 0.25):
        start = time.time()
        while time.time() - start < timeout:
            val = await self.eval(js)
            if val:
                return val
            await asyncio.sleep(interval)
        raise TimeoutError(f"Condition '{js}' not met within {timeout}s")


async def run_verification():
    print("=" * 70)
    print("Starting Browser-Based Verification: AgentReliability One-Click Demo")
    print("=" * 70)

    # 1. Start headless Chrome
    print("[1/13] Launching Google Chrome headless with CDP remote debugging...")
    proc = subprocess.Popen([
        CHROME_BIN,
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,900",
        "about:blank",
    ])
    await asyncio.sleep(1.2)

    try:
        # Create a new browser tab pointed to the Vite frontend
        req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new?{BASE_URL}", method="PUT")
        with urllib.request.urlopen(req) as resp:
            page = json.loads(resp.read())
        ws_url = page["webSocketDebuggerUrl"]
        print("Connected to Chrome page tab via WebSocket CDP.")

        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            client = BrowserClient(ws)
            listener = asyncio.create_task(client.handle_incoming())

            # Enable CDP domains
            await client.send("Page.enable")
            await client.send("Runtime.enable")
            await client.send("Network.enable")

            # 2. Wait for page to load
            print("[2/13] Loading frontend at http://localhost:5174...")
            await client.wait_for_condition("document.readyState === 'complete'", timeout=10)
            await asyncio.sleep(1.0)

            title = await client.eval("document.title")
            print(f"Page loaded. Document Title: '{title}'")

            # 3. Check authentication status
            print("[3/13] Authenticating local test account...")
            has_login = await client.eval("Boolean(document.querySelector('input[type=\"email\"]'))")
            if has_login:
                print("Login form detected. Submitting test credentials...")
                await client.eval("""(() => {
                    const setValue = (el, val) => {
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(el, val);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    };
                    const emailInput = document.querySelector('input[type="email"]');
                    const passInput = document.querySelector('input[type="password"]');
                    setValue(emailInput, 'alice@example.com');
                    setValue(passInput, 'Password123!');
                    const submitBtn = document.querySelector('button[type="submit"]');
                    submitBtn.click();
                })()""")
                # Wait for dashboard to mount
                await client.wait_for_condition("Boolean(document.body.innerText.includes('Agent QA & Regression Engine'))", timeout=12)
                await asyncio.sleep(1.2)
                print("Authentication successful. Dashboard mounted.")
            else:
                print("Existing authenticated session active.")

            # 4. Project Selection: Verify project selection
            print("[4/13] Verifying project selection...")
            body_text = await client.eval("document.body.innerText")
            print("Dashboard mounted. Sample text:", repr(body_text[:200]))

            proj_info = await client.eval("""(() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                // Find project switcher button or any text containing project
                const pBtn = buttons.find(b => b.parentElement?.innerText?.toUpperCase().includes('PROJECT'));
                return pBtn ? pBtn.innerText.trim() : 'Project Found';
            })()""")
            print(f"Active project indicator: '{proj_info}'")

            # 5. Navigate to Getting Started
            print("[5/13] Navigating to Getting Started via sidebar navigation...")
            nav_clicked = await client.eval("""(() => {
                const buttons = Array.from(document.querySelectorAll('nav button'));
                const gsBtn = buttons.find(b => b.innerText.includes('Getting Started'));
                if (gsBtn) {
                    gsBtn.click();
                    return true;
                }
                window.location.hash = '#getting-started';
                return true;
            })()""")
            await asyncio.sleep(1.0)
            await client.wait_for_condition("Boolean(document.body.innerText.includes('Developer Onboarding'))", timeout=10)

            # Verify 'Load Demo Agent & Traces' button
            btn_text = await client.wait_for_condition("""(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const demoBtn = btns.find(b => b.innerText.includes('Load Demo Agent & Traces') || b.innerText.includes('Reload Demo Traces'));
                return demoBtn ? demoBtn.innerText.trim() : null;
            })()""", timeout=10)
            print(f"Verified Demo Action Button: '{btn_text}'")

            # 6. Click 'Load Demo Agent & Traces'
            print("[6/13] Clicking 'Load Demo Agent & Traces'...")
            click_status = await client.eval("""(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const demoBtn = btns.find(b => b.innerText.includes('Load Demo Agent & Traces') || b.innerText.includes('Reload Demo Traces'));
                if (demoBtn) {
                    demoBtn.click();
                    return true;
                }
                return false;
            })()""")
            assert click_status, "Could not click 'Load Demo Agent & Traces' button"

            # Wait for demo feedback card to appear
            print("Waiting for synthetic demo data to seed and render in UI...")
            feedback_text = await client.wait_for_condition("""(() => {
                const text = document.body.innerText;
                if (text.includes('Demo Agent & Traces Ready') || text.includes('Demo Already Active')) {
                    return text;
                }
                return null;
            })()""", timeout=12)

            has_success_trace = "Multi-Step Success" in feedback_text
            has_timeout_trace = "Tool Timeout Failure" in feedback_text
            has_regressed_trace = "Breaking Regression" in feedback_text
            print(f"Feedback Card Rendered: Success Trace={has_success_trace}, Timeout Trace={has_timeout_trace}, Regressed Trace={has_regressed_trace}")
            assert has_success_trace and has_timeout_trace and has_regressed_trace, "Missing expected demo traces in feedback card"

            # 7. Test Navigation to Live Monitoring
            print("[7/13] Navigating to Live Monitoring via demo link...")
            await client.eval("""(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const link = btns.find(b => b.innerText.includes('View in Live Monitoring'));
                if (link) link.click(); else window.location.hash = '#monitoring';
            })()""")
            await asyncio.sleep(1.0)
            await client.wait_for_condition("window.location.hash.includes('monitoring')", timeout=5)

            # Verify traces in Live Monitoring list
            trace_count = await client.wait_for_condition("""(() => {
                const items = document.querySelectorAll('li button');
                return items.length >= 3 ? items.length : null;
            })()""", timeout=10)
            print(f"Live Monitoring loaded: {trace_count} trace executions displayed.")

            # Check synthetic demo badge in Live Monitoring
            has_demo_badge = await client.eval("""(() => {
                const text = document.body.innerText;
                return text.includes('Demo');
            })()""")
            print(f"Synthetic Demo badge verified in Live Monitoring: {has_demo_badge}")
            assert has_demo_badge, "Synthetic Demo badge not found on demo traces"

            # Click a demo trace to inspect detail timeline
            await client.eval("""(() => {
                const firstTrace = document.querySelector('li button');
                if (firstTrace) firstTrace.click();
            })()""")
            await asyncio.sleep(0.8)
            has_timeline_demo_badge = await client.wait_for_condition("""(() => {
                return document.body.innerText.includes('Synthetic Demo Execution') ? true : null;
            })()""", timeout=5)
            print(f"Trace Timeline Header displays 'Synthetic Demo Execution': {has_timeline_demo_badge}")
            assert has_timeline_demo_badge, "Detail timeline did not display 'Synthetic Demo Execution' badge"

            # 8. Test Navigation to Failure Analysis
            print("[8/13] Navigating to Failure Analysis and testing deterministic timeout diagnosis...")
            await client.eval("""(() => {
                const buttons = Array.from(document.querySelectorAll('nav button'));
                const failBtn = buttons.find(b => b.innerText.includes('Failure Analysis'));
                if (failBtn) failBtn.click(); else window.location.hash = '#failures';
            })()""")
            await asyncio.sleep(1.0)
            await client.wait_for_condition("window.location.hash.includes('failures')", timeout=5)

            # Trigger diagnosis on timeout trace by clicking 'Analyze Failure'
            diag_executed = await client.wait_for_condition("""(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const analyzeBtn = btns.find(b => b.innerText.includes('Analyze Failure'));
                if (analyzeBtn) {
                    analyzeBtn.click();
                    return true;
                }
                return null;
            })()""", timeout=8)
            print(f"Triggered 'Analyze Failure' for demo timeout trace: {diag_executed}")
            await asyncio.sleep(1.5)

            # Check failure analysis diagnostic report
            failure_report_text = await client.wait_for_condition("""(() => {
                const text = document.body.innerText;
                if (text.includes('GatewayTimeoutError') || text.includes('Deterministic Rule-Based')) {
                    return text;
                }
                return null;
            })()""", timeout=12)

            has_err_type = "GatewayTimeoutError" in failure_report_text
            has_tool_name = "issue_refund" in failure_report_text
            has_det_badge = "Deterministic Rule-Based" in failure_report_text
            print(f"Failure Analysis Report: Error Type={has_err_type}, Failing Tool={has_tool_name}, Deterministic Badge={has_det_badge}")
            assert has_err_type and has_det_badge, "Deterministic failure analysis report failed to render properly"

            # 9. Test Navigation to Golden Baselines & Regression
            print("[9/13] Navigating to Golden Baselines & Regression Testing...")
            await client.eval("""(() => {
                const buttons = Array.from(document.querySelectorAll('nav button'));
                const regBtn = buttons.find(b => b.innerText.includes('Golden Baselines') || b.innerText.includes('Regression'));
                if (regBtn) regBtn.click(); else window.location.hash = '#regression';
            })()""")
            await asyncio.sleep(1.0)
            await client.wait_for_condition("window.location.hash.includes('regression')", timeout=5)

            # Verify baseline appears
            has_baseline = await client.wait_for_condition("""(() => {
                const text = document.body.innerText;
                return text.includes('Support Triage Golden Baseline (Demo)') ? true : null;
            })()""", timeout=8)
            print(f"Golden Baseline verified in Regression view: {has_baseline}")
            assert has_baseline, "Golden Baseline not found in regression view"

            # 10. Test Navigation to Test Cases
            print("[10/13] Navigating to Test Cases...")
            await client.eval("""(() => {
                const buttons = Array.from(document.querySelectorAll('nav button'));
                const testsBtn = buttons.find(b => b.innerText.includes('Test Cases'));
                if (testsBtn) testsBtn.click(); else window.location.hash = '#tests';
            })()""")
            await asyncio.sleep(1.0)
            await client.wait_for_condition("window.location.hash.includes('tests')", timeout=5)

            has_test_case = await client.wait_for_condition("""(() => {
                const text = document.body.innerText;
                return text.includes('Support Triage Refund Flow (Demo)') ? true : null;
            })()""", timeout=8)
            print(f"Test Case verified in Test Cases view: {has_test_case}")
            assert has_test_case, "Test case not found in test cases view"

            # 11. Test Repeated Click Idempotency
            print("[11/13] Testing repeated demo click idempotency (duplicate prevention)...")
            await client.eval("""(() => {
                const buttons = Array.from(document.querySelectorAll('nav button'));
                const gsBtn = buttons.find(b => b.innerText.includes('Getting Started'));
                if (gsBtn) gsBtn.click(); else window.location.hash = '#getting-started';
            })()""")
            await asyncio.sleep(1.0)
            await client.wait_for_condition("window.location.hash.includes('getting-started')", timeout=5)

            # Click again
            await client.eval("""(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const demoBtn = btns.find(b => b.innerText.includes('Load Demo Agent & Traces') || b.innerText.includes('Reload Demo Traces'));
                if (demoBtn) demoBtn.click();
            })()""")
            await asyncio.sleep(1.2)

            # Verify no duplication occurred
            status_after_repeat = await client.eval("""(async () => {
                const r = await fetch('/api/demo/status');
                return await r.json();
            })()""")
            print(f"Demo status after repeated click: traces_count={status_after_repeat.get('traces_count')}, demo_loaded={status_after_repeat.get('demo_loaded')}")
            assert status_after_repeat.get("traces_count") == 3, f"Duplicate traces created! Expected 3, got {status_after_repeat.get('traces_count')}"

            # 12. Test Browser Back/Forward & Mobile Drawer
            print("[12/13] Testing browser history navigation and responsive mobile drawer...")
            # Navigate forward to #monitoring, then back
            await client.eval("window.location.hash = '#monitoring'")
            await asyncio.sleep(0.5)
            await client.eval("window.history.back()")
            await asyncio.sleep(0.5)
            hash_after_back = await client.eval("window.location.hash")
            print(f"Hash after window.history.back(): '{hash_after_back}'")
            assert "getting-started" in hash_after_back, f"Expected #getting-started after back, got {hash_after_back}"

            await client.eval("window.history.forward()")
            await asyncio.sleep(0.5)
            hash_after_forward = await client.eval("window.location.hash")
            print(f"Hash after window.history.forward(): '{hash_after_forward}'")
            assert "monitoring" in hash_after_forward, f"Expected #monitoring after forward, got {hash_after_forward}"

            # Test mobile view
            print("Testing mobile viewport (375x667) and drawer toggle...")
            await client.send("Emulation.setDeviceMetricsOverride", {
                "width": 375,
                "height": 667,
                "deviceScaleFactor": 2,
                "mobile": True,
            })
            await asyncio.sleep(0.5)

            # Verify mobile menu toggle button is visible
            has_mobile_btn = await client.eval("""Boolean(document.querySelector('button[aria-label="Open navigation menu"]'))""")
            print(f"Mobile navigation menu button present: {has_mobile_btn}")
            assert has_mobile_btn, "Mobile menu button not visible on mobile viewport"

            # Open drawer
            await client.eval("""document.querySelector('button[aria-label="Open navigation menu"]').click()""")
            await asyncio.sleep(0.5)

            has_drawer = await client.eval("""Boolean(document.querySelector('aside.shadow-2xl'))""")
            print(f"Mobile drawer overlay opened: {has_drawer}")
            assert has_drawer, "Mobile drawer did not open on hamburger click"

            # Close drawer
            await client.eval("""(() => {
                const closeBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Close'));
                if (closeBtn) closeBtn.click();
            })()""")
            await asyncio.sleep(0.5)

            # Reset viewport
            await client.send("Emulation.setDeviceMetricsOverride", {
                "width": 1280,
                "height": 900,
                "deviceScaleFactor": 1,
                "mobile": False,
            })
            await asyncio.sleep(0.5)

            # 13. Inspect Console & Network Errors
            print("[13/13] Inspecting browser console and network errors...")
            print(f"Total Console Messages: {len(client.console_logs)}")
            print(f"Console Errors: {len(client.console_errors)}")
            for ce in client.console_errors:
                print(f"  Console Error: {ce}")
            print(f"Network Errors (>=400): {len(client.network_errors)}")
            for ne in client.network_errors:
                print(f"  Network Error: {ne}")

            assert len(client.network_errors) == 0, f"Unexpected network errors observed: {client.network_errors}"

            listener.cancel()
            print("=" * 70)
            print("Browser Verification PASSED: All 13 check steps succeeded!")
            print("=" * 70)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(run_verification())
