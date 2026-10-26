"""Pydantic schemas for authentication and account management."""
from __future__ import annotations

import re
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = Field(default="", max_length=100)

    @field_validator("email")
    def validate_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not EMAIL_REGEX.match(cleaned):
            raise ValueError("Invalid email address format.")
        return cleaned

    @field_validator("password")
    def validate_password(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError("Password must contain at least 8 characters.")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    created_at: str

    @field_validator("created_at", mode="before")
    def format_created_at(cls, v: Any) -> str:
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    def validate_password(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError("Password must contain at least 8 characters.")
        return v


class AuthMessageResponse(BaseModel):
    message: str
    dev_reset_token: Optional[str] = None

