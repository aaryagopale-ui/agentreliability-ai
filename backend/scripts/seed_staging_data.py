#!/usr/bin/env python3
"""Synthetic Staging Seed Script for AgentReliability AI.

Guarantees:
1. Purely Synthetic: Uses mock accounts and dummy agent execution traces.
2. Zero PII / Zero Production Secrets: Never imports real user data or live API keys.
3. Multi-Tenant Ready: Seeds two distinct developer tenants (Alpha & Beta) to enable
   immediate cross-tenant isolation smoke-testing in staging.
4. Database Engine Agnostic: Works with SQLite locally or PostgreSQL in staging.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import auth_store, database, project_store
from app.security import hash_password


SYNTHETIC_USERS = [
    {
        "email": "staging-alpha@agentreliability.dev",
        "name": "Alpha Staging Lead",
        "password": "StagingPassword123!",
        "project_name": "Support Bot (Staging)",
    },
    {
        "email": "staging-beta@agentreliability.dev",
        "name": "Beta Staging Lead",
        "password": "StagingPassword123!",
        "project_name": "Triage Agent (Staging)",
    },
]


def seed_synthetic_staging_data(db_conn=None) -> dict:
    """Populate database with isolated synthetic test accounts and projects."""
    created_records = {"users": [], "projects": [], "api_keys": []}

    for u in SYNTHETIC_USERS:
        # Check if user already exists
        existing = auth_store.get_user_by_email(u["email"])
        if existing:
            print(f"[*] Synthetic user already exists: {u['email']} (id={existing['id']})")
            user_id = existing["id"]
        else:
            pw_hash = hash_password(u["password"])
            user = auth_store.create_user(u["email"], pw_hash, u["name"])
            user_id = user["id"]
            print(f"[+] Created synthetic user: {u['email']} (id={user_id})")
            created_records["users"].append(u["email"])

        # Check projects for this user
        projects = project_store.list_user_projects(user_id)
        if not projects:
            proj = project_store.create_project(u["project_name"], user_id)
            proj_id = proj["id"]
            print(f"[+] Created synthetic project '{u['project_name']}' (id={proj_id})")
            created_records["projects"].append(u["project_name"])
            # Generate a staging test API key
            key_rec, raw_key = project_store.create_api_key(proj_id, "Staging Ingestion Key")
            print(f"[+] Generated staging API key prefix: {key_rec['key_prefix']} (id={key_rec['id']})")
            created_records["api_keys"].append(key_rec["key_prefix"])
        else:
            print(f"[*] Projects already exist for user id={user_id}")

    return created_records


def main():
    parser = argparse.ArgumentParser(description="Seed synthetic data for AgentReliability AI staging")
    parser.add_argument("--confirm", action="store_true", help="Confirm execution of staging seed")
    args = parser.parse_args()

    if not args.confirm:
        print("[!] Safety gate: Re-run with --confirm to seed synthetic staging accounts.")
        sys.exit(0)

    print("[*] Seeding synthetic staging data...")
    res = seed_synthetic_staging_data()
    print("[+] Staging seeding completed successfully.")
    print(f"    Users: {len(res['users'])}, Projects: {len(res['projects'])}, Keys: {len(res['api_keys'])}")


if __name__ == "__main__":
    main()

