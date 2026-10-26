"""Evidence-Based AI Failure Analysis Engine.

Performs deterministic, rule-based diagnostic extraction from recorded execution traces:
- Categorizes failure mode.
- Locates the failing step and failing tool call.
- Assembles chronological preceding events.
- Flags measurable timing anomalies and duration spikes.
- Integrates baseline regression differences when available.
- Separates confirmed ground-truth observations from hypothetical explanations.
- Assigns evidence sufficiency scores (sufficient, partial, insufficient).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .redaction import global_redactor


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return json.dumps(val, default=str)


def diagnose_failure(
    execution: Optional[dict],
    tool_calls: Optional[List[dict]] = None,
    regression_comparison: Optional[dict] = None,
) -> dict:
    """Produce a deterministic, evidence-grounded failure diagnosis report.

    Guarantees:
    - Never fabricates stack traces or non-existent error causes.
    - Strictly reports recorded facts as 'confirmed_observations' and 'facts'.
    - Distinguishes observed facts from possible causes.
    - Provides practical debugging suggestions based on observed failure category.
    - Handles missing, sparse, or malformed trace data gracefully.
    - Accurately rates evidence sufficiency.
    """
    exec_dict = execution if isinstance(execution, dict) else {}
    tools = [t for t in (tool_calls or []) if isinstance(t, dict)]

    exec_id = exec_dict.get("execution_id") or str(exec_dict.get("id") or "unknown")
    agent_name = str(exec_dict.get("agent_name") or "Agent")
    exec_status = str(exec_dict.get("status") or "unknown").lower()
    failure_kind = str(exec_dict.get("failure_kind") or "").lower()
    exec_error_type = str(exec_dict.get("error_type") or "")
    exec_error_msg = str(exec_dict.get("error_message") or "")

    try:
        raw_dur = exec_dict.get("duration_ms")
        exec_duration = float(raw_dur) if raw_dur is not None else None
    except (ValueError, TypeError):
        exec_duration = None

    # Sanitize error strings to ensure zero leaked secrets
    clean_error_type = global_redactor.sanitize_text(exec_error_type, max_chars=200) or ""
    clean_error_msg = global_redactor.sanitize_text(exec_error_msg, max_chars=1000) or ""

    confirmed_observations: List[str] = []
    deterministic_recommendations: List[str] = []
    timing_anomalies: List[dict] = []
    preceding_events: List[dict] = []

    # 1. Inspect tool calls to find failing tools and preceding sequence
    failing_tool = None
    failed_tool_index = -1

    for idx, t in enumerate(tools):
        t_status = str(t.get("status") or "").lower()
        t_err = str(t.get("error_message") or t.get("error") or "")
        t_name = str(t.get("tool_name") or t.get("name") or f"tool_{idx}")
        try:
            t_dur = float(t.get("duration_ms")) if t.get("duration_ms") is not None else None
        except (ValueError, TypeError):
            t_dur = None
        try:
            t_retries = int(t.get("retry_count", 0) or 0)
        except (ValueError, TypeError):
            t_retries = 0

        # Check for individual tool failure
        is_tool_failed = t_status in ("error", "failed", "timeout", "exception") or bool(t_err)
        if is_tool_failed and failing_tool is None:
            failing_tool = t
            failed_tool_index = idx

        # Check for timing anomalies
        if t_dur is not None:
            if t_dur > 10_000:  # > 10s is a timing anomaly for a single tool call
                timing_anomalies.append({
                    "target": f"Tool '{t_name}'",
                    "duration_ms": t_dur,
                    "anomaly_type": "high_latency_step",
                    "description": f"Tool '{t_name}' took {t_dur:.1f} ms (>10,000 ms threshold).",
                })
            elif t_dur < 1.0 and is_tool_failed:
                timing_anomalies.append({
                    "target": f"Tool '{t_name}'",
                    "duration_ms": t_dur,
                    "anomaly_type": "immediate_fail_step",
                    "description": f"Tool '{t_name}' failed immediately in {t_dur:.2f} ms (likely connection refusal or syntax error).",
                })

    # Assemble preceding events (all tool calls up to the failing tool)
    if failed_tool_index >= 0:
        for idx in range(failed_tool_index):
            pt = tools[idx]
            preceding_events.append({
                "step_index": idx + 1,
                "tool_name": pt.get("tool_name") or pt.get("name"),
                "status": pt.get("status"),
                "duration_ms": pt.get("duration_ms"),
            })
    elif len(tools) > 0:
        # If no specific tool failed, record tools that ran
        for idx, pt in enumerate(tools):
            preceding_events.append({
                "step_index": idx + 1,
                "tool_name": pt.get("tool_name") or pt.get("name"),
                "status": pt.get("status"),
                "duration_ms": pt.get("duration_ms"),
            })

    # 2. Extract baseline regression differences if available
    regression_findings: List[dict] = []
    missing_tools: List[dict] = []
    breaking_diffs: List[dict] = []
    if regression_comparison and isinstance(regression_comparison, dict):
        diffs = regression_comparison.get("differences")
        if isinstance(diffs, list):
            for d in diffs:
                if not isinstance(d, dict):
                    continue
                cat = str(d.get("category") or "").lower()
                sev = str(d.get("severity") or "").lower()
                msg = str(d.get("message") or "")
                if sev in ("breaking_regression", "breaking", "performance_regression"):
                    regression_findings.append({
                        "category": d.get("category"),
                        "severity": d.get("severity"),
                        "message": msg,
                    })
                is_tool_missing = ("tool" in cat and "missing" in cat) or ("missing" in msg.lower() and "tool" in msg.lower())
                if is_tool_missing:
                    missing_tools.append(d)
                elif sev in ("breaking_regression", "breaking"):
                    breaking_diffs.append(d)

    # 3. Determine Primary Failure Category & Primary Error
    failure_category = "unknown_failure"
    primary_error_type = clean_error_type
    primary_error_message = clean_error_msg
    failing_tool_name = str(failing_tool.get("tool_name") or failing_tool.get("name")) if failing_tool else None

    # Check timeout condition
    is_timeout = (
        failure_kind == "timeout"
        or "timeout" in clean_error_msg.lower()
        or "timeout" in clean_error_type.lower()
        or (failing_tool and str(failing_tool.get("status") or "").lower() == "timeout")
    )

    if is_timeout:
        failure_category = "timeout"
        dur_str = f"{exec_duration:.1f} ms" if exec_duration is not None else "unspecified duration"
        confirmed_observations.append(f"Execution timed out. Total duration recorded: {dur_str}.")
        deterministic_recommendations.append("Check network timeouts, external API availability, and long-running model loops.")
    elif failing_tool is not None:
        failure_category = "failed_tool_call"
        t_name = failing_tool_name
        t_err_type = str(failing_tool.get("error_type") or "ToolExecutionError")
        t_err_msg = str(failing_tool.get("error_message") or failing_tool.get("error") or "Unspecified tool failure")
        if not primary_error_type:
            primary_error_type = t_err_type
        if not primary_error_message:
            primary_error_message = t_err_msg

        confirmed_observations.append(
            f"Tool '{t_name}' failed at step {failed_tool_index + 1} with error: [{t_err_type}] {t_err_msg}."
        )
        try:
            retry_cnt = int(failing_tool.get("retry_count", 0) or 0)
        except (ValueError, TypeError):
            retry_cnt = 0
        if retry_cnt > 0:
            confirmed_observations.append(
                f"Tool '{t_name}' was attempted {retry_cnt + 1} times before final failure."
            )
            deterministic_recommendations.append(
                f"Review retry policy for tool '{t_name}'. Successive retries failed to resolve the error."
            )
        deterministic_recommendations.append(
            f"Verify parameters and environment permissions for tool '{t_name}'."
        )
    elif missing_tools and (exec_status == "failed" or (regression_comparison and regression_comparison.get("regression_detected"))):
        failure_category = "missing_tool_call"
        missing_msg = "; ".join(d.get("message", "") for d in missing_tools)
        confirmed_observations.append(f"Missing required tool call: {missing_msg}")
        deterministic_recommendations.append("Inspect agent tool-calling prompt, descriptions, and conditional routing paths.")
    elif breaking_diffs and (exec_status == "failed" or (regression_comparison and regression_comparison.get("regression_detected"))):
        failure_category = "breaking_regression"
        diff_msg = "; ".join(d.get("message", "") for d in breaking_diffs)
        confirmed_observations.append(f"Breaking regression against baseline: {diff_msg}")
        deterministic_recommendations.append("Inspect output schema changes or lock a new Golden Baseline version if intentional.")
    elif failure_kind == "unexpected_exception" or primary_error_type:
        failure_category = "unexpected_exception"
        confirmed_observations.append(
            f"Agent terminated with unhandled exception: [{primary_error_type}] {primary_error_message}."
        )
        deterministic_recommendations.append(
            f"Add error handling in agent execution loop for {primary_error_type}."
        )
    elif exec_status == "failed" or primary_error_message:
        failure_category = "explicit_error"
        confirmed_observations.append(
            f"Execution marked as failed with message: '{primary_error_message or 'No error message recorded'}'."
        )
        deterministic_recommendations.append("Inspect business logic assertions and input validation steps.")
    elif exec_status == "success":
        failure_category = "none"
        confirmed_observations.append("Execution completed successfully without errors.")
    else:
        failure_category = "unknown_failure"
        confirmed_observations.append("Execution status or failure cause could not be determined from available trace evidence.")

    # Record regression observation items
    for reg in regression_findings:
        msg = f"Regression detected: {reg.get('message')}"
        if msg not in confirmed_observations:
            confirmed_observations.append(msg)

    # 4. Construct Structured, Evidence-Based Failure Explanation
    facts: List[str] = list(confirmed_observations)
    possible_causes: List[str] = []
    debugging_suggestions: List[str] = list(deterministic_recommendations)
    relevant_tool_name = failing_tool_name

    if failure_category == "timeout":
        dur_text = f"{exec_duration:.1f} ms" if exec_duration is not None else "duration limit"
        tool_clause = f" while executing tool '{failing_tool_name}'" if failing_tool_name else ""
        summary_text = f"Execution timed out after {dur_text}{tool_clause}."
        possible_causes = [
            "Downstream network service stalled or failed to respond within the allowed timeout window.",
            "Long-running recursive or iterative prompt loop inside the agent workflow.",
            "Configured timeout threshold is insufficient for cold-start latency or large response payloads.",
        ]
        if not debugging_suggestions:
            debugging_suggestions = [
                "Inspect network timeout configurations and socket timeouts on downstream clients.",
                "Review agent prompt loop termination conditions to ensure it halts cleanly.",
                "Increase max_duration_ms baseline tolerance if high latency is expected for this workload.",
            ]
    elif failure_category in ("failed_tool_call", "tool_exception"):
        try:
            t_dur_val = float(failing_tool.get("duration_ms")) if failing_tool and failing_tool.get("duration_ms") is not None else None
            t_dur_str = f" (duration: {t_dur_val:.1f} ms)" if t_dur_val is not None else ""
        except (ValueError, TypeError):
            t_dur_str = ""

        summary_text = (
            f"Tool '{failing_tool_name}' failed at step {failed_tool_index + 1} "
            f"with [{primary_error_type or 'ToolExecutionError'}]: {primary_error_message or 'Unspecified failure'}{t_dur_str}."
        )

        err_lower = (f"{primary_error_type} {primary_error_message}").lower()
        if any(w in err_lower for w in ("connection", "refused", "unreachable", "dns", "socket", "network")):
            possible_causes = [
                f"Target endpoint or service for '{failing_tool_name}' was unreachable or refused connection.",
                "Network firewall, proxy, or sandbox restrictions blocked outbound connection.",
                "Service address/port configuration in environment variables may be incorrect.",
            ]
            debugging_suggestions.append(f"Verify endpoint host, port, and health check for '{failing_tool_name}'.")
        elif any(w in err_lower for w in ("auth", "401", "403", "forbidden", "unauthorized", "token", "key", "permission")):
            possible_causes = [
                f"Authentication credentials or API key for '{failing_tool_name}' are missing, invalid, or expired.",
                "Service role lacks required IAM permissions to perform the requested operation.",
            ]
            debugging_suggestions.append(f"Verify API keys, access tokens, and environment permissions for '{failing_tool_name}'.")
        elif any(w in err_lower for w in ("schema", "keyerror", "typeerror", "valueerror", "validation", "missing")):
            possible_causes = [
                f"Invalid or unexpected parameter structure supplied to '{failing_tool_name}'.",
                "Upstream step output may have produced unexpected data shape passed into this tool.",
            ]
            debugging_suggestions.append(f"Inspect arguments passed to '{failing_tool_name}' against expected schema.")
        elif any(w in err_lower for w in ("rate", "429", "quota", "exhausted", "throttled")):
            possible_causes = [
                f"Downstream API rate limit or quota exceeded during '{failing_tool_name}'.",
                "Burst traffic without adequate backoff/retry throttling.",
            ]
            debugging_suggestions.append(f"Implement exponential backoff or increase rate limit allocation for '{failing_tool_name}'.")
        else:
            possible_causes = [
                f"Tool '{failing_tool_name}' encountered an unhandled exception during execution.",
                "Upstream parameters may not conform to preconditions expected by tool implementation.",
            ]
    elif failure_category == "missing_tool_call":
        missing_names = [d.get("message", "") for d in missing_tools]
        summary_text = (
            f"Execution did not invoke expected tool(s) required by the Golden Baseline: {'; '.join(missing_names) if missing_names else 'missing tool'}."
        )
        possible_causes = [
            "Agent decision-making or LLM prompt response skipped expected tool invocation.",
            "Conditional branching path diverged based on intermediate step results.",
            "Tool routing prompt or function calling schema was not recognized by the model.",
        ]
        debugging_suggestions = [
            "Inspect agent prompt instructions, tool descriptions, and few-shot examples for tool calling.",
            "Review conditional branching in agent logic to ensure tool path is triggered as expected.",
            "Compare candidate trace tool sequence against Golden Baseline to locate divergence point.",
        ]
    elif failure_category == "breaking_regression":
        summary_text = (
            f"Execution completed but exhibited {len(breaking_diffs)} breaking regression(s) against Golden Baseline."
        )
        possible_causes = [
            "Agent output schema changed without updating the Golden Baseline definition.",
            "Prompt engineering modifications altered the output structure or keys.",
            "Upstream dependency change caused downstream output divergence.",
        ]
        debugging_suggestions = [
            "Inspect baseline regression differences to review added, removed, or type-altered fields.",
            "If output format change is intentional, publish a new Golden Baseline version.",
            "If output change is a defect, enforce schema validation before agent completes.",
        ]
    elif failure_category in ("unexpected_exception", "explicit_error"):
        dur_str = f" after {exec_duration:.1f} ms" if exec_duration is not None else ""
        summary_text = (
            f"Agent execution terminated with error{dur_str}: [{primary_error_type or 'ExecutionError'}] "
            f"{primary_error_message or 'No error message recorded'}."
        )
        possible_causes = [
            f"Unhandled exception raised in agent coordinator logic: {primary_error_type or 'Error'}.",
            "Explicit failure triggered due to unsatisfied business validation.",
        ]
        if not debugging_suggestions:
            debugging_suggestions = [
                f"Add defensive exception handling around agent workflow for {primary_error_type or 'errors'}.",
                "Inspect preceding tool outputs to verify that valid data was returned.",
            ]
    elif failure_category == "none":
        dur_str = f" in {exec_duration:.1f} ms" if exec_duration is not None else ""
        summary_text = f"Execution completed successfully{dur_str} with {len(tools)} tool call(s)."
        possible_causes = []
        debugging_suggestions = ["No debugging required. Execution is healthy and meets reliability criteria."]
    else:
        summary_text = "Execution status or error cause could not be definitively determined from available trace evidence."
        possible_causes = ["Trace data is incomplete, sparse, or lacks explicit error telemetry."]
        debugging_suggestions = ["Ensure AGENTRELIABILITY_CAPTURE_IO=1 is enabled and exceptions are captured with SDK instrumentation."]

    failure_explanation = {
        "summary": summary_text,
        "failure_type": failure_category,
        "relevant_tool": relevant_tool_name,
        "observed_error_type": primary_error_type or None,
        "observed_error_message": primary_error_message or None,
        "execution_status": exec_status,
        "duration_ms": exec_duration,
        "facts": facts,
        "possible_causes": possible_causes,
        "debugging_suggestions": debugging_suggestions,
    }

    # 5. Determine Evidence Sufficiency
    if failure_category == "none":
        evidence_sufficiency = "sufficient"
        confidence_score = 1.0
    elif primary_error_message and (failing_tool is not None or failure_category == "timeout"):
        evidence_sufficiency = "sufficient"
        confidence_score = 0.95
    elif primary_error_type or primary_error_message or len(tools) > 0 or missing_tools or breaking_diffs:
        evidence_sufficiency = "partial"
        confidence_score = 0.70
    else:
        evidence_sufficiency = "insufficient"
        confidence_score = 0.35
        confirmed_observations.append("Notice: Trace contains sparse error metadata. Root cause analysis is limited to recorded facts.")

    # 6. Format Final Diagnostic Report
    report = {
        "execution_id": exec_id,
        "agent_name": agent_name,
        "status": exec_status,
        "failure_category": failure_category,
        "primary_error": {
            "error_type": primary_error_type or None,
            "error_message": primary_error_message or None,
            "failing_tool": failing_tool_name,
            "failing_step_index": (failed_tool_index + 1) if failed_tool_index >= 0 else None,
        },
        "preceding_events": preceding_events,
        "timing_anomalies": timing_anomalies,
        "regression_evidence": regression_findings,
        "evidence_sufficiency": evidence_sufficiency,
        "confidence_score": confidence_score,
        "confirmed_observations": confirmed_observations,
        "deterministic_recommendations": deterministic_recommendations,
        "failure_explanation": failure_explanation,
    }
    return report

