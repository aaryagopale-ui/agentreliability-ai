"""Configuration manager for AgentReliability.

Provides safe local project configuration via .agentreliability.json.
Respects resolution order:
  1. Explicit argument / flag
  2. Shell environment variables (AGENTRELIABILITY_ENDPOINT, AGENTRELIABILITY_API_KEY)
  3. Local .agentreliability.json in current directory or workspace root
  4. Built-in defaults (http://127.0.0.1:8001, empty API key)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("agentreliability.config")

CONFIG_FILE_NAME = ".agentreliability.json"
DEFAULT_ENDPOINT = "http://127.0.0.1:8001"
DEFAULT_FRONTEND_URL = "http://127.0.0.1:5174"
DEFAULT_BACKEND_PORT = 8001
DEFAULT_FRONTEND_PORT = 5174


def generate_instance_id(workspace_root: Union[str, Path]) -> str:
    """Generate a stable, deterministic instance ID based on the workspace path."""
    resolved = str(Path(workspace_root).resolve())
    h = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]
    return f"ar_inst_{h}"


def resolve_instance_id(start_dir: Optional[Union[str, Path]] = None) -> str:
    """Resolve instance ID for current workspace."""
    cfg = load_config(start_dir)
    cfg_val = cfg.get("instance_id")
    if cfg_val and str(cfg_val).strip():
        return str(cfg_val).strip()

    root = find_workspace_root(start_dir)
    if root:
        return generate_instance_id(root)

    target = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
    return generate_instance_id(target)


def resolve_database_path(
    explicit: Optional[Union[str, Path]] = None,
    start_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Resolve absolute database path according to precedence rules."""
    if explicit and str(explicit).strip():
        return Path(explicit).resolve()

    env_val = os.environ.get("AGENTRELIABILITY_DB")
    if env_val and env_val.strip():
        return Path(env_val.strip()).resolve()

    cfg = load_config(start_dir)
    cfg_val = cfg.get("database_path")
    if cfg_val and str(cfg_val).strip():
        return Path(cfg_val.strip()).resolve()

    root = find_workspace_root(start_dir)
    if root:
        return (root / "backend" / "agentreliability.db").resolve()

    return (Path.cwd() / "backend" / "agentreliability.db").resolve()



def find_workspace_root(start_dir: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Search upward from start_dir for AgentReliability workspace root."""
    current = Path(start_dir or Path.cwd()).resolve()

    for candidate in [current] + list(current.parents):
        # 1. Direct configuration file presence
        if (candidate / CONFIG_FILE_NAME).is_file():
            return candidate

        # 2. Workspace root markers (backend and sdk directories)
        if (candidate / "backend" / "app" / "main.py").is_file() and (candidate / "sdk" / "pyproject.toml").is_file():
            return candidate

        # 3. Git root check
        if (candidate / ".git").is_dir() and (candidate / "backend").is_dir():
            return candidate

    return None


def load_config(start_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Load configuration from .agentreliability.json if available.

    Returns empty dictionary if file does not exist or cannot be read.
    """
    base = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
    root = find_workspace_root(base)
    config_path = (root / CONFIG_FILE_NAME) if root else (base / CONFIG_FILE_NAME)

    if not config_path.is_file():
        return {}

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        logger.warning("Configuration file %s is not a valid JSON dictionary.", config_path)
    except Exception as exc:
        logger.warning("Failed to parse configuration file %s: %s", config_path, exc)

    return {}


def save_config(config_data: Dict[str, Any], target_dir: Optional[Union[str, Path]] = None) -> Path:
    """Save configuration to .agentreliability.json in workspace root or target directory."""
    if target_dir:
        dest_dir = Path(target_dir).resolve()
    else:
        root = find_workspace_root()
        dest_dir = root if root else Path.cwd().resolve()

    dest_dir.mkdir(parents=True, exist_ok=True)
    config_path = dest_dir / CONFIG_FILE_NAME

    # Merge with existing configuration if present
    merged: Dict[str, Any] = {}
    if config_path.is_file():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                merged.update(existing)
        except Exception:
            pass

    merged.update(config_data)

    content = json.dumps(merged, indent=2, sort_keys=True) + "\n"
    config_path.write_text(content, encoding="utf-8")
    return config_path


def resolve_endpoint(
    explicit: Optional[str] = None,
    start_dir: Optional[Union[str, Path]] = None,
) -> str:
    """Resolve backend endpoint according to precedence rules."""
    if explicit and str(explicit).strip():
        return str(explicit).strip().rstrip("/")

    env_val = os.environ.get("AGENTRELIABILITY_ENDPOINT")
    if env_val and env_val.strip():
        return env_val.strip().rstrip("/")

    cfg = load_config(start_dir)
    cfg_val = cfg.get("backend_url")
    if cfg_val and str(cfg_val).strip():
        return str(cfg_val).strip().rstrip("/")

    return DEFAULT_ENDPOINT


def resolve_api_key(
    explicit: Optional[str] = None,
    start_dir: Optional[Union[str, Path]] = None,
) -> str:
    """Resolve project API key according to precedence rules."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()

    env_val = os.environ.get("AGENTRELIABILITY_API_KEY")
    if env_val and env_val.strip():
        return env_val.strip()

    cfg = load_config(start_dir)
    cfg_val = cfg.get("api_key")
    if cfg_val and str(cfg_val).strip():
        return str(cfg_val).strip()

    return ""
