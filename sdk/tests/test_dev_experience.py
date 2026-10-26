"""Tests for developer experience: init, dev, doctor, port resolution, and configuration."""
import io
import json
import os
import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

import pytest
from agentreliability.cli import main
from agentreliability.config import (
    CONFIG_FILE_NAME,
    DEFAULT_ENDPOINT,
    find_workspace_root,
    load_config,
    resolve_api_key,
    resolve_endpoint,
    save_config,
)
from agentreliability.dev_server import (
    find_backend_python,
    initialize_local_database,
    run_dev,
    run_init,
)
from agentreliability.doctor import (
    check_backend_and_auth,
    check_database,
    check_node_and_frontend,
    check_ports,
    check_python,
    run_doctor,
)
from agentreliability.ports import (
    find_available_port,
    is_port_available,
    is_port_in_use,
    probe_backend,
    probe_frontend,
    resolve_service_ports,
)


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# 1. Configuration Management Tests
# ---------------------------------------------------------------------------

def test_config_save_load_merge(tmp_path: Path):
    saved_path = save_config({"backend_port": 8002, "backend_url": "http://127.0.0.1:8002"}, target_dir=tmp_path)
    assert saved_path.is_file()
    assert saved_path.name == CONFIG_FILE_NAME

    loaded = load_config(tmp_path)
    assert loaded["backend_port"] == 8002
    assert loaded["backend_url"] == "http://127.0.0.1:8002"

    save_config({"frontend_port": 5176}, target_dir=tmp_path)
    updated = load_config(tmp_path)
    assert updated["backend_port"] == 8002
    assert updated["frontend_port"] == 5176


def test_config_resolution_precedence(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AGENTRELIABILITY_ENDPOINT", raising=False)
    monkeypatch.delenv("AGENTRELIABILITY_API_KEY", raising=False)
    assert resolve_endpoint(start_dir=tmp_path) == DEFAULT_ENDPOINT
    assert resolve_api_key(start_dir=tmp_path) == ""

    save_config({"backend_url": "http://127.0.0.1:8099", "api_key": "cfg_key_abc"}, target_dir=tmp_path)
    assert resolve_endpoint(start_dir=tmp_path) == "http://127.0.0.1:8099"
    assert resolve_api_key(start_dir=tmp_path) == "cfg_key_abc"

    monkeypatch.setenv("AGENTRELIABILITY_ENDPOINT", "http://127.0.0.1:9999")
    monkeypatch.setenv("AGENTRELIABILITY_API_KEY", "env_key_xyz")
    assert resolve_endpoint(start_dir=tmp_path) == "http://127.0.0.1:9999"
    assert resolve_api_key(start_dir=tmp_path) == "env_key_xyz"

    assert resolve_endpoint("http://127.0.0.1:7777", start_dir=tmp_path) == "http://127.0.0.1:7777"
    assert resolve_api_key("param_key_123", start_dir=tmp_path) == "param_key_123"


def test_config_invalid_json(tmp_path: Path):
    bad_cfg = tmp_path / CONFIG_FILE_NAME
    bad_cfg.write_text("NOT_VALID_JSON{:::}", encoding="utf-8")
    loaded = load_config(tmp_path)
    assert loaded == {}


# ---------------------------------------------------------------------------
# 2. Port Detection & Conflict Resolution Tests
# ---------------------------------------------------------------------------

def test_port_availability_and_in_use():
    free_p = get_free_port()
    assert is_port_available(free_p)
    assert not is_port_in_use(free_p)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", free_p))
    try:
        assert is_port_in_use(free_p)
        assert not is_port_available(free_p)
    finally:
        s.close()


def test_find_available_port_skips_occupied():
    free_p = get_free_port()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", free_p))
    try:
        next_free = find_available_port(free_p)
        assert next_free != free_p
        assert next_free > free_p
        assert is_port_available(next_free)
    finally:
        s.close()


def test_probe_backend_offline():
    free_p = get_free_port()
    probe = probe_backend(free_p)
    assert not probe["occupied"]
    assert not probe["is_agentreliability"]


def test_probe_backend_compatible_agentreliability(monkeypatch):
    occupied_port = 8001
    monkeypatch.setattr("agentreliability.ports.is_port_in_use", lambda p, h="127.0.0.1": True)
    monkeypatch.setattr("agentreliability.ports.is_port_available", lambda p, h="127.0.0.1": False)

    def mock_urlopen(req, timeout=1.5):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        if "/api/health" in url:
            cm.headers = {"X-Service": "agentreliability-backend", "X-Service-Version": "0.1.0"}
            cm.read.return_value = b'{"status": "ok"}'
        elif "/api/v1/system/info" in url:
            cm.headers = {}
            cm.read.return_value = b'{"service": "agentreliability-backend", "version": "0.1.0", "multi_tenant": true}'
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    probe = probe_backend(occupied_port)
    assert probe["occupied"] is True
    assert probe["is_agentreliability"] is True
    assert probe["compatible"] is True
    assert probe["healthy"] is True
    assert probe["version"] == "0.1.0"
    assert probe["multi_tenant"] is True


def test_probe_backend_unrelated_process(monkeypatch):
    occupied_port = 8001
    monkeypatch.setattr("agentreliability.ports.is_port_in_use", lambda p, h="127.0.0.1": True)
    monkeypatch.setattr("agentreliability.ports.is_port_available", lambda p, h="127.0.0.1": False)

    def mock_urlopen(req, timeout=1.5):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    probe = probe_backend(occupied_port)
    assert probe["occupied"] is True
    assert probe["is_agentreliability"] is False
    assert probe["compatible"] is False


def test_resolve_service_ports_free(monkeypatch):
    free_b = 8001
    free_f = 5174
    monkeypatch.setattr("agentreliability.ports.is_port_in_use", lambda p, h="127.0.0.1": False)
    monkeypatch.setattr("agentreliability.ports.is_port_available", lambda p, h="127.0.0.1": True)

    b_port, reuse_b, f_port, reuse_f = resolve_service_ports(
        preferred_backend_port=free_b,
        preferred_frontend_port=free_f,
    )
    assert b_port == free_b
    assert reuse_b is False
    assert f_port == free_f
    assert reuse_f is False


def test_resolve_service_ports_reuse_compatible_backend(monkeypatch):
    target_b = 8001
    target_f = 5174

    def mock_probe_backend(p, h="127.0.0.1", timeout=1.5):
        if p == target_b:
            return {"occupied": True, "is_agentreliability": True, "compatible": True, "healthy": True}
        return {"occupied": False, "is_agentreliability": False}

    monkeypatch.setattr("agentreliability.ports.probe_backend", mock_probe_backend)
    monkeypatch.setattr("agentreliability.ports.probe_frontend", lambda p, h="127.0.0.1", timeout=1.5: {"occupied": False})

    b_port, reuse_b, f_port, reuse_f = resolve_service_ports(
        preferred_backend_port=target_b,
        preferred_frontend_port=target_f,
    )
    assert b_port == target_b
    assert reuse_b is True  # Reused!
    assert f_port == target_f
    assert reuse_f is False


def test_resolve_service_ports_conflict_unrelated_fallback(monkeypatch):
    occupied_b = 8001
    target_f = 5174

    def mock_probe_backend(p, h="127.0.0.1", timeout=1.5):
        if p == occupied_b:
            return {"occupied": True, "is_agentreliability": False, "compatible": False}
        return {"occupied": False, "is_agentreliability": False}

    monkeypatch.setattr("agentreliability.ports.probe_backend", mock_probe_backend)
    monkeypatch.setattr("agentreliability.ports.probe_frontend", lambda p, h="127.0.0.1", timeout=1.5: {"occupied": False})
    monkeypatch.setattr("agentreliability.ports.is_port_available", lambda p, h="127.0.0.1": p != occupied_b)
    monkeypatch.setattr("agentreliability.ports.is_port_in_use", lambda p, h="127.0.0.1": p == occupied_b)

    b_port, reuse_b, f_port, reuse_f = resolve_service_ports(
        preferred_backend_port=occupied_b,
        preferred_frontend_port=target_f,
    )
    assert b_port != occupied_b
    assert b_port == 8002  # Automatically selected next available port
    assert reuse_b is False


# ---------------------------------------------------------------------------
# 3. System Doctor Tests
# ---------------------------------------------------------------------------

def test_doctor_python_checks():
    py = check_python()
    assert py["valid_version"] is True
    assert "version" in py
    assert isinstance(py["missing_packages"], list)


def test_doctor_node_checks():
    fe = check_node_and_frontend()
    assert "node_bin" in fe
    assert "npm_bin" in fe
    assert "has_node_modules" in fe


def test_doctor_database_checks(tmp_path: Path):
    db_res = check_database()
    assert "exists" in db_res
    assert "ok" in db_res


def test_doctor_backend_and_auth_probe(monkeypatch):
    def mock_urlopen(req, timeout=3.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        cm = MagicMock()
        cm.__enter__.return_value = cm
        cm.__exit__.return_value = False
        cm.status = 200
        if "/api/health" in url:
            cm.read.return_value = b'{"status": "ok"}'
        elif "/api/v1/auth/verify" in url:
            key = req.headers.get("X-api-key") or req.headers.get("X-API-Key")
            if key == "valid_key_test_123":
                cm.read.return_value = b'{"status": "valid", "project": {"name": "Test Project"}}'
            else:
                raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
        return cm

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    endpoint = "http://127.0.0.1:8001"
    # Valid key
    res_valid = check_backend_and_auth(endpoint, "valid_key_test_123")
    assert res_valid["healthy"] is True
    assert res_valid["api_key_valid"] is True
    assert res_valid["project_name"] == "Test Project"

    # Invalid key
    res_invalid = check_backend_and_auth(endpoint, "wrong_key_xyz")
    assert res_invalid["healthy"] is True
    assert res_invalid["api_key_valid"] is False


def test_doctor_cli_command(capsys):
    ret = main(["doctor"])
    captured = capsys.readouterr()
    assert "AgentReliability System Doctor" in captured.out
    assert "[Python Environment]" in captured.out
    assert "[Ports & Network]" in captured.out
    assert ret in (0, 1)


# ---------------------------------------------------------------------------
# 4. Init & Dev Command Tests
# ---------------------------------------------------------------------------

def test_init_command_creates_config(tmp_path: Path, monkeypatch):
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("# main", encoding="utf-8")
    (tmp_path / "sdk").mkdir()
    (tmp_path / "sdk" / "pyproject.toml").write_text("# sdk", encoding="utf-8")
    (tmp_path / "frontend").mkdir()

    monkeypatch.chdir(tmp_path)

    with patch("agentreliability.dev_server.initialize_local_database", return_value=(True, "Mock DB initialized")):
        ret = run_init()
        assert ret == 0

    cfg_file = tmp_path / CONFIG_FILE_NAME
    assert cfg_file.is_file()
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "backend_port" in cfg
    assert "backend_url" in cfg
    assert "frontend_port" in cfg
    assert "frontend_url" in cfg


def test_init_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["init", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "Check prerequisites, create local config" in captured.out


def test_dev_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["dev", "--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "automatic port conflict resolution" in captured.out
    assert "--backend-port" in captured.out


def test_dev_reused_active_backend(tmp_path: Path, monkeypatch, capsys):
    target_b = 8001
    monkeypatch.setattr(
        "agentreliability.dev_server.resolve_service_ports",
        lambda preferred_backend_port, preferred_frontend_port, host="127.0.0.1": (target_b, True, 5174, True),
    )
    with patch("agentreliability.dev_server.find_workspace_root", return_value=tmp_path):
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            ret = run_dev(backend_port=target_b, backend_only=True, no_banner=True)
            assert ret == 0
            captured = capsys.readouterr()
            assert "Reusing instance" in captured.out


def test_dev_early_subprocess_failure(tmp_path: Path, monkeypatch, capsys):
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("# main", encoding="utf-8")
    (tmp_path / "sdk").mkdir()
    (tmp_path / "sdk" / "pyproject.toml").write_text("# sdk", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    monkeypatch.chdir(tmp_path)

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 1
    mock_proc.returncode = 1
    mock_proc.communicate.return_value = ("", "ModuleNotFoundError: No module named 'fastapi'")

    monkeypatch.setattr(
        "agentreliability.dev_server.resolve_service_ports",
        lambda preferred_backend_port, preferred_frontend_port, host="127.0.0.1": (8001, False, 5174, False),
    )
    monkeypatch.setattr("agentreliability.dev_server.find_backend_python", lambda root: (sys.executable, []))
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: mock_proc)

    ret = run_dev(backend_only=True, no_banner=True)
    assert ret == 1
    captured = capsys.readouterr()
    assert "Backend exited unexpectedly" in captured.err
    assert "ModuleNotFoundError" in captured.err
