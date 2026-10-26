"""Pydantic schemas for project and API key management."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    def clean_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Project name cannot be empty or whitespace.")
        return s


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    def clean_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Project name cannot be empty or whitespace.")
        return s


class ProjectDelete(BaseModel):
    confirm_name: str = Field(description="Must match the exact project name to confirm deletion/archival.")


class ProjectResponse(BaseModel):
    id: int
    name: str
    owner_id: Optional[int]
    created_at: str
    updated_at: Optional[str] = None
    archived_at: Optional[str] = None

    @field_validator("created_at", "updated_at", "archived_at", mode="before")
    def format_timestamps(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)


class ProjectWithKeyResponse(BaseModel):
    id: int
    name: str
    owner_id: Optional[int]
    created_at: str
    api_key: str  # Plaintext key returned ONCE at creation

    @field_validator("created_at", mode="before")
    def format_created_at(cls, v: Any) -> str:
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)


class ApiKeyCreate(BaseModel):
    name: Optional[str] = Field(default="API Key", max_length=100)

    @field_validator("name")
    def clean_name(cls, v: Optional[str]) -> str:
        s = (v or "").strip()
        return s if s else "API Key"


class ApiKeyResponse(BaseModel):
    id: int
    project_id: int
    name: str
    key_prefix: str
    created_at: str
    last_used_at: Optional[str] = None
    revoked_at: Optional[str] = None

    @field_validator("created_at", "last_used_at", "revoked_at", mode="before")
    def format_timestamps(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)


class ApiKeyCreatedResponse(BaseModel):
    id: int
    project_id: int
    name: str
    key_prefix: str
    created_at: str

    @field_validator("created_at", mode="before")
    def format_created_at(cls, v: Any) -> str:
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)
    api_key: str  # Plaintext key returned ONCE at creation/rotation

