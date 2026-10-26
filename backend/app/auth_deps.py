"""Centralized authorization dependencies for AgentReliability AI (Phase 5A Step 5).

Provides reusable FastAPI dependencies for:
1. Browser session authentication (`get_current_user`)
2. Double-submit CSRF verification (`check_csrf`, `require_csrf`)
3. Multi-tenant project resolution & ownership authorization (`get_authorized_project`)
4. Resource-level access control with anti-enumeration protection (returns 404 for foreign or non-existent resources)
5. Project-scoped API key authentication (`require_api_key_project`)
"""
from __future__ import annotations

from typing import Optional
from fastapi import Depends, Header, HTTPException, Query, Request, status

from . import ci_store, database, project_store, test_store, trace_store
from .auth_api import check_csrf, get_current_user


def require_api_key_project(x_api_key: Optional[str] = Header(default=None)) -> dict:
    """Dependency: Validate X-API-Key header and resolve active project.
    Returns project dict {"id": ..., "name": ...}.
    """
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key. Send it in the X-API-Key header.")
    project = trace_store.find_project_by_key(x_api_key)
    if project is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
    return project


def require_csrf(request: Request) -> None:
    """Dependency enforcing CSRF protection on mutating browser requests."""
    check_csrf(request)


def get_authorized_project(
    request: Request,
    project_id: Optional[int] = Query(default=None),
    x_project_id: Optional[int] = Header(default=None, alias="X-Project-Id"),
    user: dict = Depends(get_current_user),
) -> dict:
    """Resolve and verify the active project for the authenticated browser user.

    Security rules:
    - If an explicit project ID is provided (via header or query parameter),
      verify that it exists and is owned by the current user.
    - If the project does not exist or belongs to another tenant, return HTTP 404
      (anti-enumeration: never leak that another tenant's project exists).
    - If no project ID is provided, fall back to the user's default/first active project.
    - If the user has no active projects, return HTTP 404.
    """
    target_id = x_project_id if x_project_id is not None else project_id

    if target_id is not None:
        proj = project_store.get_project(target_id, owner_id=user["id"])
        if not proj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )
        return proj

    user_projects = project_store.list_user_projects(user["id"])
    if not user_projects:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active project found for user. Please create a project first.",
        )
    return user_projects[0]


def require_owned_execution(
    exec_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    """Resource-level authorizer for Agent Executions.
    Returns 404 if execution does not exist or is not owned by the current user.
    """
    execution = database.get_execution(exec_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")

    proj_id = execution.get("project_id", 1)
    proj = project_store.get_project(proj_id, owner_id=user["id"])
    if not proj:
        # Anti-enumeration: treat foreign projects as not found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")

    return execution


def require_owned_test_case(
    case_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    """Resource-level authorizer for Test Cases.
    Returns 404 if test case does not exist or is not owned by the current user.
    """
    case = test_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found.")

    proj_id = case.get("project_id", 1)
    proj = project_store.get_project(proj_id, owner_id=user["id"])
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found.")

    return case


def require_owned_test_run(
    run_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    """Resource-level authorizer for Test Runs.
    Returns 404 if test run does not exist or is not owned by the current user.
    """
    run = test_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test run not found.")

    proj_id = run.get("project_id", 1)
    proj = project_store.get_project(proj_id, owner_id=user["id"])
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test run not found.")

    return run


def require_owned_trace(
    execution_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Resource-level authorizer for Trace Executions.
    Returns 404 if trace does not exist or is not owned by the current user.
    """
    trace = trace_store.get_execution(execution_id)
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")

    proj_id = trace.get("project_id", 1)
    proj = project_store.get_project(proj_id, owner_id=user["id"])
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")

    return trace


def require_owned_ci_run(
    run_id: int,
    user: dict = Depends(get_current_user),
) -> dict:
    """Resource-level authorizer for CI Runs.
    Returns 404 if CI run does not exist or is not owned by the current user.
    """
    run = ci_store.get_ci_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CI test run not found.")

    proj_id = run.get("project_id", 1)
    proj = project_store.get_project(proj_id, owner_id=user["id"])
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CI test run not found.")

    return run
