"""Build clean, sanitized distribution package for private developer pilot.

Strictly excludes:
- Local SQLite databases (*.db, *.sqlite, *.db-shm, *.db-wal, *.bak)
- Python virtual environments (.venv, venv, .venv-*)
- Node modules (node_modules/)
- Build artifacts (dist/, build/, .egg-info/)
- Bytecode caches (__pycache__, *.pyc)
- Secrets, credentials, and .env files (except *.example)
- Run logs, scratch files, and internal session transcripts
"""
from __future__ import annotations

import hashlib
import os
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
ARCHIVE_NAME = "agentreliability-pilot-v0.1.0.tar.gz"
ARCHIVE_PATH = DIST_DIR / ARCHIVE_NAME

BANNED_EXACT_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    ".env",
    ".agentreliability.json",
    "agentreliability.db",
    "agentreliability.db-shm",
    "agentreliability.db-wal",
    "results.json",
    "failure-results.json",
}

BANNED_DIR_PARTS = {
    ".venv",
    ".venv-crewai",
    ".venv-crewai312",
    "venv",
    "venv-crewai312",
    ".agentreliability",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".vite",
    ".gemini",
    "dist",
    "build",
    "agentreliability.egg-info",
}

BANNED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".bak",
    ".log",
    ".jsonl",
    ".shm",
    ".wal",
    ".so",
}

# Explicit inclusion trees and root files
INCLUDED_ROOT_FILES = [
    "START_HERE.md",
    "README.md",
    "start.sh",
    "start.bat",
    "demo_agent.py",
    "example_agent.py",
    ".gitignore",
]

INCLUDED_DIRECTORIES = [
    "backend",
    "sdk",
    "frontend",
    "examples",
    "docs",
]


def is_safe_file(rel_path: Path) -> bool:
    """Return True if a file is explicitly safe for distribution."""
    parts = set(rel_path.parts)
    if any(banned in parts for banned in BANNED_DIR_PARTS):
        return False
    if rel_path.name in BANNED_EXACT_NAMES:
        return False
    if rel_path.suffix.lower() in BANNED_SUFFIXES:
        return False
    if rel_path.name.startswith(".env") and not rel_path.name.endswith(".example"):
        return False
    if "agentreliability.db" in rel_path.name:
        return False
    return True


def collect_pilot_files() -> list[Path]:
    collected: list[Path] = []

    # Root files
    for rf_name in INCLUDED_ROOT_FILES:
        rf = REPO_ROOT / rf_name
        if rf.is_file() and is_safe_file(Path(rf_name)):
            collected.append(rf)

    # Directories
    for d_name in INCLUDED_DIRECTORIES:
        d_path = REPO_ROOT / d_name
        if not d_path.is_dir():
            continue
        for root, dirs, files in os.walk(d_path):
            # Prune banned directories in-place
            dirs[:] = [d for d in dirs if d not in BANNED_DIR_PARTS and not d.startswith(".venv")]
            for f in files:
                full_path = Path(root) / f
                rel = full_path.relative_to(REPO_ROOT)
                if is_safe_file(rel):
                    collected.append(full_path)

    return sorted(collected)


def sha256_of_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def main():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    files = collect_pilot_files()
    print(f"📦 Collected {len(files)} safe source files for pilot distribution.")

    # Validation pass: guarantee 0 prohibited files
    for f in files:
        rel = f.relative_to(REPO_ROOT)
        assert is_safe_file(rel), f"PROHIBITED FILE DETECTED: {rel}"
        # Extra assertion: ensure no database files
        assert not rel.name.endswith(".db"), f"DATABASE DETECTED: {rel}"
        assert "venv" not in str(rel).lower() or "examples" in str(rel), f"VENV DETECTED: {rel}"
        assert "node_modules" not in str(rel), f"NODE_MODULES DETECTED: {rel}"

    # Build tar.gz archive
    print(f"🗜️  Creating archive at {ARCHIVE_PATH}...")
    prefix_dir = "AgentReliability-pilot-v0.1.0"
    with tarfile.open(ARCHIVE_PATH, "w:gz") as tar:
        for f in files:
            rel = f.relative_to(REPO_ROOT)
            arcname = f"{prefix_dir}/{rel}"
            tar.add(f, arcname=arcname)

    archive_size_bytes = ARCHIVE_PATH.stat().st_size
    archive_hash = sha256_of_file(ARCHIVE_PATH)

    print("\n✅ Private Pilot Source Package Built Successfully!")
    print(f"   Archive Path : {ARCHIVE_PATH}")
    print(f"   Size         : {archive_size_bytes / 1024:.1f} KB ({archive_size_bytes} bytes)")
    print(f"   SHA-256      : {archive_hash}")
    print(f"   Files Total  : {len(files)} source files")

    # Write manifest alongside archive
    manifest_path = DIST_DIR / "agentreliability-pilot-v0.1.0-manifest.txt"
    with open(manifest_path, "w", encoding="utf-8") as mf:
        mf.write(f"# AgentReliability AI Private Developer Pilot Manifest\n")
        mf.write(f"# Package: {ARCHIVE_NAME}\n")
        mf.write(f"# SHA-256: {archive_hash}\n")
        mf.write(f"# Total Files: {len(files)}\n\n")
        for f in files:
            rel = f.relative_to(REPO_ROOT)
            mf.write(f"{rel}\n")

    print(f"   Manifest     : {manifest_path}\n")


if __name__ == "__main__":
    main()

