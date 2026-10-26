"""Project and API Key Management API router.

Endpoints:
  GET    /api/projects                             - List user projects
  POST   /api/projects                             - Create project (returns initial key once)
  GET    /api/projects/{id}                        - Get project details
  PATCH  /api/projects/{id}                        - Rename project
  DELETE /api/projects/{id}                        - Soft-delete / archive project (requires confirmation)
  POST   /api/projects/{id}/claim                  - Claim unowned legacy project
  GET    /api/projects/{id}/keys                   - List project API keys
  POST   /api/projects/{id}/keys                   - Generate new project API key
  DELETE /api/projects/{id}/keys/{key_id}          - Revoke project API key
  POST   /api/projects/{id}/keys/{key_id}/rotate   - Rotate project API key
"""
from __future__ import annotations

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status

from . import project_store
from .auth_api import check_csrf, get_current_user
from .project_schemas import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    ProjectCreate,
    ProjectDelete,
    ProjectResponse,
    ProjectUpdate,
    ProjectWithKeyResponse,
)

router = APIRouter(prefix="/api/projects", tags=["Projects"])


def get_user_project(project_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: Ensures project exists, is not archived, and is owned by the current user.
    Returns 404 on access denial to prevent project ID enumeration.
    """
    proj = project_store.get_project(project_id, owner_id=current_user["id"])
    if not proj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return proj


# -----------------------------------------------------------------------------
# Project Endpoints
# -----------------------------------------------------------------------------

@router.get("", response_model=List[ProjectResponse])
def list_projects(current_user: dict = Depends(get_current_user)):
    return project_store.list_user_projects(current_user["id"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectWithKeyResponse)
def create_project(body: ProjectCreate, request: Request, current_user: dict = Depends(get_current_user)):
    check_csrf(request)
    proj, plaintext_key = project_store.create_project(body.name, current_user["id"])
    return ProjectWithKeyResponse(
        id=proj["id"],
        name=proj["name"],
        owner_id=proj["owner_id"],
        created_at=proj["created_at"],
        api_key=plaintext_key,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project: dict = Depends(get_user_project)):
    return ProjectResponse(**project)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    body: ProjectUpdate,
    request: Request,
    project: dict = Depends(get_user_project),
    current_user: dict = Depends(get_current_user),
):
    check_csrf(request)
    updated = project_store.update_project_name(project["id"], body.name, current_user["id"])
    if not updated:
        raise HTTPException(status_code=400, detail="Failed to update project name.")
    return ProjectResponse(**updated)


@router.delete("/{project_id}")
def delete_project(
    body: ProjectDelete,
    request: Request,
    project: dict = Depends(get_user_project),
    current_user: dict = Depends(get_current_user),
):
    check_csrf(request)
    if body.confirm_name.strip() != project["name"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Confirmation name '{body.confirm_name}' does not match project name '{project['name']}'.",
        )
    archived = project_store.archive_project(project["id"], current_user["id"])
    if not archived:
        raise HTTPException(status_code=400, detail="Failed to archive project.")
    return {"message": "Project archived successfully."}


@router.post("/{project_id}/claim", response_model=ProjectResponse)
def claim_legacy_project(
    project_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Claim an unowned legacy project (where owner_id is NULL)."""
    check_csrf(request)
    claimed = project_store.claim_legacy_project(project_id, current_user["id"])
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Legacy project not found or already owned.",
        )
    return project_store.get_project(project_id, current_user["id"])


# -----------------------------------------------------------------------------
# API Key Endpoints
# -----------------------------------------------------------------------------

@router.get("/{project_id}/keys", response_model=List[ApiKeyResponse])
def list_api_keys(project: dict = Depends(get_user_project)):
    return project_store.list_project_keys(project["id"])


@router.post("/{project_id}/keys", status_code=status.HTTP_201_CREATED, response_model=ApiKeyCreatedResponse)
def create_api_key(
    body: ApiKeyCreate,
    request: Request,
    project: dict = Depends(get_user_project),
):
    check_csrf(request)
    key_record, plaintext_key = project_store.create_api_key(project["id"], body.name or "API Key")
    return ApiKeyCreatedResponse(
        id=key_record["id"],
        project_id=key_record["project_id"],
        name=key_record["name"],
        key_prefix=key_record["key_prefix"],
        created_at=key_record["created_at"],
        api_key=plaintext_key,
    )


@router.delete("/{project_id}/keys/{key_id}")
def revoke_api_key(
    key_id: int,
    request: Request,
    project: dict = Depends(get_user_project),
):
    check_csrf(request)
    revoked = project_store.revoke_api_key(project["id"], key_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found or already revoked.")
    return {"message": "API key revoked successfully."}


@router.post("/{project_id}/keys/{key_id}/rotate", response_model=ApiKeyCreatedResponse)
def rotate_api_key(
    key_id: int,
    request: Request,
    project: dict = Depends(get_user_project),
):
    check_csrf(request)
    result = project_store.rotate_api_key(project["id"], key_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    new_record, new_plaintext = result
    return ApiKeyCreatedResponse(
        id=new_record["id"],
        project_id=new_record["project_id"],
        name=new_record["name"],
        key_prefix=new_record["key_prefix"],
        created_at=new_record["created_at"],
        api_key=new_plaintext,
    )

