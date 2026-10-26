"""Deterministic regression comparison engine.

Compares a candidate agent execution against a saved regression baseline.
Accurately categorizes differences into:
- breaking_regression (missing tool, unexpected error, status change, missing output key)
- performance_regression (duration exceeded threshold)
- informational_change (benign output value change, extra allowed tool)
- inconclusive (missing evidence or incomplete trace)

Guarantees:
- Never claims semantic correctness solely from string matches.
- Transparently reports exact recorded evidence for every detected difference.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


def _norm(val: Any) -> str:
    if isinstance(val, str):
        return val.strip()
    return json.dumps(val, sort_keys=True, default=str)


def try_parse_json(val: Any) -> Any:
    """Safely parse a string as a JSON object or array if valid; otherwise return val as is."""
    if isinstance(val, str):
        trimmed = val.strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
    return val


def compare_execution_to_baseline(
    baseline: dict,
    candidate: dict,
    duration_tolerance_pct: float = 50.0,
) -> dict:
    """Compare a candidate execution/trace against a baseline version.

    Parameters:
      baseline: dict with keys: agent_name, status, duration_ms, input, output, tools, expected
      candidate: dict with keys: agent_name, status, duration_ms, input, output, tool_calls, error_type, error_message
      duration_tolerance_pct: percentage slowdown that flags a performance regression (default 50.0%)

    Returns:
      Comprehensive regression report dict.
    """
    diffs: List[dict] = []
    breaking_count = 0
    perf_count = 0
    info_count = 0

    cand_status = candidate.get("status", "unknown")
    base_status = baseline.get("status", "unknown")

    # Inconclusive check: candidate still running
    if cand_status == "running":
        return {
            "verdict": "inconclusive",
            "summary": "Candidate execution is still running. Inconclusive comparison.",
            "is_regression": False,
            "differences": [{
                "category": "execution_incomplete",
                "severity": "inconclusive",
                "message": "Candidate execution has not finished yet.",
                "evidence": {"candidate_status": cand_status},
            }],
            "counts": {"breaking": 0, "performance": 0, "informational": 0, "total": 1},
            "baseline": {"status": base_status, "duration_ms": baseline.get("duration_ms")},
            "candidate": {"status": cand_status, "duration_ms": candidate.get("duration_ms")},
        }

    expected = baseline.get("expected") or {}
    strict_order = expected.get("strict_order", True)
    allow_additional = expected.get("allow_additional_tools", False)

    # 1. Execution Status Comparison
    if base_status == "success" and cand_status == "failed":
        diffs.append({
            "category": "status_regression",
            "severity": "breaking_regression",
            "message": f"Execution status regressed: baseline passed ('{base_status}'), but candidate failed ('{cand_status}').",
            "evidence": {
                "baseline_status": base_status,
                "candidate_status": cand_status,
                "error_type": candidate.get("error_type"),
                "error_message": candidate.get("error_message"),
            },
        })
        breaking_count += 1
    elif cand_status != base_status:
        diffs.append({
            "category": "status_change",
            "severity": "informational_change",
            "message": f"Execution status changed from '{base_status}' to '{cand_status}'.",
            "evidence": {"baseline_status": base_status, "candidate_status": cand_status},
        })
        info_count += 1

    # 2. Tool Calls Comparison
    base_tools = baseline.get("tools") or []
    cand_tools = candidate.get("tool_calls") or []

    base_seq = [t.get("tool_name") or t.get("name") for t in base_tools if (t.get("tool_name") or t.get("name"))]
    cand_seq = [t.get("tool_name") or t.get("name") for t in cand_tools if (t.get("tool_name") or t.get("name"))]

    # Check for missing expected tools
    missing_tools = [t for t in base_seq if t not in cand_seq]
    if missing_tools:
        diffs.append({
            "category": "missing_tool_call",
            "severity": "breaking_regression",
            "message": f"Missing expected tool call(s): {missing_tools}.",
            "evidence": {"baseline_tools": base_seq, "candidate_tools": cand_seq, "missing": missing_tools},
        })
        breaking_count += 1

    # Check for unexpected additional tools
    if not allow_additional:
        extra_tools = [t for t in cand_seq if t not in base_seq]
        if extra_tools:
            diffs.append({
                "category": "unexpected_tool_call",
                "severity": "breaking_regression",
                "message": f"Unexpected tool call(s) not in baseline: {extra_tools}.",
                "evidence": {"baseline_tools": base_seq, "candidate_tools": cand_seq, "unexpected": extra_tools},
            })
            breaking_count += 1

    # Check tool sequence order
    if strict_order and base_seq and cand_seq:
        if base_seq != cand_seq:
            # Report order difference if set is equal or subset
            pos = next((i for i, (a, b) in enumerate(zip(base_seq, cand_seq)) if a != b), min(len(base_seq), len(cand_seq)))
            diffs.append({
                "category": "tool_sequence_mismatch",
                "severity": "breaking_regression",
                "message": f"Tool call sequence differs at step {pos + 1}: expected '{base_seq[pos] if pos < len(base_seq) else 'end'}', observed '{cand_seq[pos] if pos < len(cand_seq) else 'end'}'.",
                "evidence": {"expected_sequence": base_seq, "observed_sequence": cand_seq},
            })
            breaking_count += 1

    # Check for newly failed tool calls
    cand_failed_tools = [t for t in cand_tools if t.get("status") in ("error", "failed", "timeout")]
    base_failed_tools = [t for t in base_tools if t.get("status") in ("error", "failed", "timeout")]
    base_failed_names = {t.get("tool_name") or t.get("name") for t in base_failed_tools}

    for ft in cand_failed_tools:
        tname = ft.get("tool_name") or ft.get("name")
        if tname not in base_failed_names:
            diffs.append({
                "category": "newly_failed_tool",
                "severity": "breaking_regression",
                "message": f"Tool '{tname}' failed with {ft.get('error_type') or 'Error'}: {ft.get('error_message') or 'no error message'}.",
                "evidence": {"tool_name": tname, "status": ft.get("status"), "error": ft.get("error_message")},
            })
            breaking_count += 1

    # 3. Output Schema & Required Output Keys
    raw_base_out = baseline.get("output")
    raw_cand_out = candidate.get("output")

    if raw_base_out is not None:
        if raw_cand_out is None and cand_status == "success":
            diffs.append({
                "category": "missing_output",
                "severity": "breaking_regression",
                "message": "Candidate produced no output, but baseline has recorded output.",
                "evidence": {"baseline_output": raw_base_out, "candidate_output": None},
            })
            breaking_count += 1
        else:
            base_out = try_parse_json(raw_base_out)
            cand_out = try_parse_json(raw_cand_out)

            if isinstance(base_out, dict):
                if not isinstance(cand_out, dict):
                    diffs.append({
                        "category": "output_schema_mismatch",
                        "severity": "breaking_regression",
                        "message": f"Output schema changed: baseline returned dict, candidate returned {type(cand_out).__name__}.",
                        "evidence": {"baseline_type": "dict", "candidate_type": type(cand_out).__name__},
                    })
                    breaking_count += 1
                else:
                    # Check required output fields
                    req_fields = expected.get("expected_output_fields") or list(base_out.keys())
                    missing_keys = [k for k in req_fields if k not in cand_out]
                    if missing_keys:
                        diffs.append({
                            "category": "missing_output_field",
                            "severity": "breaking_regression",
                            "message": f"Missing expected output field(s): {missing_keys}.",
                            "evidence": {"required_fields": req_fields, "candidate_keys": list(cand_out.keys())},
                        })
                        breaking_count += 1
                    else:
                        # Check unexpected added fields if restricted
                        if expected.get("allow_additional_output_fields") is False or expected.get("strict_output_schema") is True:
                            extra_fields = [k for k in cand_out.keys() if k not in base_out]
                            if extra_fields:
                                diffs.append({
                                    "category": "unexpected_output_field",
                                    "severity": "breaking_regression",
                                    "message": f"Unexpected output field(s) not in baseline: {extra_fields}.",
                                    "evidence": {"baseline_fields": list(base_out.keys()), "candidate_fields": list(cand_out.keys()), "unexpected": extra_fields},
                                })
                                breaking_count += 1

                        # Check incompatible field types
                        for k in req_fields:
                            if k in cand_out and k in base_out:
                                b_val = base_out[k]
                                c_val = cand_out[k]
                                if b_val is not None and c_val is not None:
                                    b_num = isinstance(b_val, (int, float)) and not isinstance(b_val, bool)
                                    c_num = isinstance(c_val, (int, float)) and not isinstance(c_val, bool)
                                    if b_num and c_num:
                                        pass  # numeric compatibility (e.g. 100 vs 100.0)
                                    elif type(b_val) is not type(c_val):
                                        diffs.append({
                                            "category": "field_type_mismatch",
                                            "severity": "breaking_regression",
                                            "message": f"Output field '{k}' type changed: expected {type(b_val).__name__}, candidate returned {type(c_val).__name__}.",
                                            "evidence": {
                                                "field": k,
                                                "expected_type": type(b_val).__name__,
                                                "candidate_type": type(c_val).__name__,
                                                "baseline_value": b_val,
                                                "candidate_value": c_val,
                                            },
                                        })
                                        breaking_count += 1

                        # Compare output values
                        for k, b_val in base_out.items():
                            if k in cand_out and _norm(b_val) != _norm(cand_out[k]):
                                diffs.append({
                                    "category": "output_value_change",
                                    "severity": "informational_change",
                                    "message": f"Output field '{k}' value differs from baseline.",
                                    "evidence": {"key": k, "baseline_value": b_val, "candidate_value": cand_out[k]},
                                })
                                info_count += 1

            elif isinstance(base_out, list):
                if not isinstance(cand_out, list):
                    diffs.append({
                        "category": "output_schema_mismatch",
                        "severity": "breaking_regression",
                        "message": f"Output schema changed: baseline returned list, candidate returned {type(cand_out).__name__}.",
                        "evidence": {"baseline_type": "list", "candidate_type": type(cand_out).__name__},
                    })
                    breaking_count += 1
                elif _norm(base_out) != _norm(cand_out):
                    diffs.append({
                        "category": "output_value_change",
                        "severity": "informational_change",
                        "message": "Output list differs from baseline.",
                        "evidence": {"baseline_output": base_out, "candidate_output": cand_out},
                    })
                    info_count += 1

            elif _norm(base_out) != _norm(cand_out):
                diffs.append({
                    "category": "output_value_change",
                    "severity": "informational_change",
                    "message": "Output value differs from baseline.",
                    "evidence": {"baseline_output": raw_base_out, "candidate_output": raw_cand_out},
                })
                info_count += 1

    # 4. Timing & Duration Comparison
    base_dur = baseline.get("duration_ms")
    cand_dur = candidate.get("duration_ms")
    max_allowed_dur = expected.get("max_duration_ms")

    if max_allowed_dur is not None and cand_dur is not None and cand_dur > max_allowed_dur:
        diffs.append({
            "category": "duration_threshold_exceeded",
            "severity": "breaking_regression",
            "message": f"Candidate duration ({cand_dur:.1f} ms) exceeded maximum allowed limit ({max_allowed_dur:.1f} ms).",
            "evidence": {"candidate_duration_ms": cand_dur, "max_duration_ms": max_allowed_dur},
        })
        breaking_count += 1
    elif base_dur and cand_dur and base_dur > 0:
        pct_change = ((cand_dur - base_dur) / base_dur) * 100.0
        if pct_change > duration_tolerance_pct:
            diffs.append({
                "category": "latency_regression",
                "severity": "performance_regression",
                "message": f"Execution latency increased by {pct_change:.1f}% ({cand_dur:.1f} ms vs baseline {base_dur:.1f} ms, tolerance {duration_tolerance_pct}%).",
                "evidence": {
                    "baseline_duration_ms": base_dur,
                    "candidate_duration_ms": cand_dur,
                    "percent_change": round(pct_change, 1),
                },
            })
            perf_count += 1

    # Overall Verdict
    if breaking_count > 0:
        verdict = "regression"
        summary = f"Regressions detected ({breaking_count} breaking difference{'s' if breaking_count > 1 else ''})."
    elif perf_count > 0:
        verdict = "performance_warning"
        summary = f"Performance regression: latency exceeded threshold by {perf_count} check{'s' if perf_count > 1 else ''}."
    elif info_count > 0:
        verdict = "passed"
        summary = f"Passed with {info_count} non-breaking informational difference{'s' if info_count > 1 else ''}."
    else:
        verdict = "passed"
        summary = "All regression checks passed. Behavior exactly matches baseline."

    return {
        "verdict": verdict,
        "is_regression": breaking_count > 0,
        "summary": summary,
        "differences": diffs,
        "counts": {
            "breaking": breaking_count,
            "performance": perf_count,
            "informational": info_count,
            "total": len(diffs),
        },
        "baseline": {
            "status": base_status,
            "duration_ms": base_dur,
            "tool_count": len(base_tools),
            "tool_sequence": base_seq,
        },
        "candidate": {
            "status": cand_status,
            "duration_ms": cand_dur,
            "tool_count": len(cand_tools),
            "tool_sequence": cand_seq,
        },
    }

