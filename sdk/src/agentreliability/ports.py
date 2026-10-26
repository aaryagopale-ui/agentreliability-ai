"""Cross-platform port inspection, health probing, and collision resolution.

Ensures that:
1. Occupied ports 8001 and 5174 are automatically detected.
2. If occupied, compatible AgentReliability instances are verified and safely reused.
3. Unrelated or incompatible processes are NEVER terminated automatically;
   instead, an alternative free port is chosen and configured.
"""
from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("agentreliability.ports")


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Test if a port can be bound for listening on host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is currently listening or bound on host."""
    if not is_port_available(port, host):
        return True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            return s.connect_ex((host, port)) == 0
        except OSError:
            return False


def find_available_port(start_port: int, max_attempts: int = 100, host: str = "127.0.0.1") -> int:
    """Search for the next available port starting from start_port."""
    for candidate in range(start_port, start_port + max_attempts):
        if is_port_available(candidate, host) and not is_port_in_use(candidate, host):
            return candidate
    raise RuntimeError(
        f"Unable to find an available port in range {start_port}–{start_port + max_attempts - 1} on {host}."
    )


def probe_backend(
    port: int,
    host: str = "127.0.0.1",
    timeout: float = 1.5,
    expected_instance_id: Optional[str] = None,
    expected_db_path: Optional[Union[str, Any]] = None,
) -> Dict[str, Any]:
    """Probe a port to determine if an existing compatible AgentReliability backend is active."""
    in_use = is_port_in_use(port, host) or not is_port_available(port, host)
    if not in_use:
        return {
            "occupied": False,
            "is_agentreliability": False,
            "compatible": False,
            "healthy": False,
            "version": None,
            "instance_id": None,
            "database_path": None,
            "same_installation": False,
            "multi_tenant": False,
            "details": "Port is available",
        }

    # Port is in use — probe health endpoint
    health_url = f"http://{host}:{port}/api/health"
    req = urllib.request.Request(
        health_url,
        headers={"User-Agent": "agentreliability-probe/0.1.0"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            body_bytes = resp.read()
            headers = dict(resp.headers)
            body = {}
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                pass

            is_ok = status_code == 200 and body.get("status") == "ok"
            service_header = headers.get("X-Service", "") or headers.get("x-service", "")

            # If service header is present or endpoint matches our health schema
            if service_header == "agentreliability-backend" or (is_ok and "database" not in body):
                version = headers.get("X-Service-Version", "0.1.0")
                instance_id = headers.get("X-Instance-ID")
                database_path = None
                workspace_root = None
                multi_tenant = True

                try:
                    info_req = urllib.request.Request(
                        f"http://{host}:{port}/api/v1/system/info",
                        headers={"User-Agent": "agentreliability-probe/0.1.0"},
                    )
                    with urllib.request.urlopen(info_req, timeout=1.0) as info_resp:
                        info_data = json.loads(info_resp.read().decode("utf-8"))
                        version = info_data.get("version", version)
                        instance_id = info_data.get("instance_id", instance_id)
                        database_path = info_data.get("database_path")
                        workspace_root = info_data.get("workspace_root")
                        multi_tenant = info_data.get("multi_tenant", True)
                except Exception:
                    pass

                # Check if this backend belongs to the same installation / database
                same_installation = True
                if expected_instance_id or expected_db_path:
                    same_installation = False
                    if expected_instance_id and instance_id and expected_instance_id == instance_id:
                        same_installation = True
                    elif expected_db_path and database_path:
                        try:
                            from pathlib import Path
                            same_installation = Path(expected_db_path).resolve() == Path(database_path).resolve()
                        except Exception:
                            same_installation = False

                compatible = bool(is_ok and same_installation)
                if not same_installation:
                    details = f"Separate AgentReliability instance active (ID: {instance_id or 'unknown'}, DB: {database_path or 'unknown'})"
                else:
                    details = f"Compatible AgentReliability backend running (v{version}, instance: {instance_id or 'local'})"

                return {
                    "occupied": True,
                    "is_agentreliability": True,
                    "compatible": compatible,
                    "healthy": is_ok,
                    "version": version,
                    "instance_id": instance_id,
                    "database_path": database_path,
                    "workspace_root": workspace_root,
                    "same_installation": same_installation,
                    "multi_tenant": multi_tenant,
                    "details": details,
                }

            # Responded 200 but not AgentReliability
            return {
                "occupied": True,
                "is_agentreliability": False,
                "compatible": False,
                "healthy": False,
                "version": None,
                "multi_tenant": False,
                "details": "Occupied by an unrelated service responding to /api/health",
            }

    except urllib.error.HTTPError as exc:
        # HTTP error response (e.g. 404 Not Found, 502, 503)
        return {
            "occupied": True,
            "is_agentreliability": False,
            "compatible": False,
            "healthy": False,
            "version": None,
            "multi_tenant": False,
            "details": f"Occupied by a service returning HTTP {exc.code}",
        }
    except Exception as exc:
        # Non-HTTP service, timeout, or connection refused
        return {
            "occupied": True,
            "is_agentreliability": False,
            "compatible": False,
            "healthy": False,
            "version": None,
            "multi_tenant": False,
            "details": f"Occupied by a non-HTTP or unresponsive process ({exc})",
        }


def probe_frontend(port: int, host: str = "127.0.0.1", timeout: float = 1.5) -> Dict[str, Any]:
    """Probe a port to determine if an AgentReliability dashboard is serving."""
    in_use = is_port_in_use(port, host) or not is_port_available(port, host)
    if not in_use:
        return {
            "occupied": False,
            "is_agentreliability": False,
            "healthy": False,
            "details": "Port is available",
        }

    url = f"http://{host}:{port}/"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "agentreliability-probe/0.1.0"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                html = resp.read().decode("utf-8", errors="replace")
                if "AgentReliability" in html or "agentreliability" in html:
                    return {
                        "occupied": True,
                        "is_agentreliability": True,
                        "healthy": True,
                        "details": "Active AgentReliability dashboard running",
                    }
            return {
                "occupied": True,
                "is_agentreliability": False,
                "healthy": False,
                "details": f"Occupied by an unrelated web service (HTTP {resp.status})",
            }
    except Exception as exc:
        return {
            "occupied": True,
            "is_agentreliability": False,
            "healthy": False,
            "details": f"Occupied by an external process ({exc})",
        }


def resolve_service_ports(
    preferred_backend_port: int = 8001,
    preferred_frontend_port: int = 5174,
    host: str = "127.0.0.1",
    expected_instance_id: Optional[str] = None,
    expected_db_path: Optional[Union[str, Any]] = None,
) -> Tuple[int, bool, int, bool]:
    """Resolve backend and frontend ports safely.

    Ensures that an active backend is ONLY reused if it matches the current
    installation's instance identity or database path.

    Returns:
      (backend_port, reuse_backend, frontend_port, reuse_frontend)
    """
    # 1. Resolve Backend
    try:
        b_probe = probe_backend(
            preferred_backend_port,
            host,
            expected_instance_id=expected_instance_id,
            expected_db_path=expected_db_path,
        )
    except TypeError:
        try:
            b_probe = probe_backend(preferred_backend_port, host)
        except TypeError:
            b_probe = probe_backend(preferred_backend_port)
    if not b_probe["occupied"]:
        backend_port = preferred_backend_port
        reuse_backend = False
    elif b_probe["is_agentreliability"] and b_probe["compatible"]:
        backend_port = preferred_backend_port
        reuse_backend = True
    else:
        # Port occupied by an unrelated service or a DIFFERENT AgentReliability installation
        backend_port = find_available_port(preferred_backend_port + 1, host=host)
        reuse_backend = False

    # 2. Resolve Frontend
    f_probe = probe_frontend(preferred_frontend_port, host)
    if not f_probe["occupied"]:
        frontend_port = preferred_frontend_port
        reuse_frontend = False
    elif f_probe["is_agentreliability"] and reuse_backend:
        # Only reuse existing frontend if the backend was also reused from the same installation
        frontend_port = preferred_frontend_port
        reuse_frontend = True
    else:
        # Port occupied or dedicated frontend needed for this installation
        frontend_port = find_available_port(preferred_frontend_port + 1, host=host)
        reuse_frontend = False

    return backend_port, reuse_backend, frontend_port, reuse_frontend

    return backend_port, reuse_backend, frontend_port, reuse_frontend
