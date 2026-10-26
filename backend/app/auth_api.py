"""Authentication API router for AgentReliability AI.

Endpoints:
  POST /api/auth/register        - Register new user
  POST /api/auth/login           - Login and set HttpOnly session cookie
  POST /api/auth/logout          - Revoke session and clear cookies
  GET  /api/auth/me              - Profile of authenticated user
  POST /api/auth/forgot-password - Request password reset token
  POST /api/auth/reset-password  - Reset password using token
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from . import auth_store
from .auth_schemas import (
    AuthMessageResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)
from .security import (
    AUTH_FAILED_MESSAGE,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    RESET_SENT_MESSAGE,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    auth_rate_limiter,
    consume_password_reset_token,
    create_password_reset_token,
    create_session,
    generate_csrf_token,
    get_cookie_samesite,
    get_cookie_secure,
    hash_password,
    revoke_all_user_sessions,
    revoke_session,
    validate_password_reset_token,
    validate_session,
    verify_csrf_token,
    verify_password,
)

logger = logging.getLogger("agentreliability.auth")
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def get_client_ip(request: Request) -> str:
    """Extract client IP address for rate limiting."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def enforce_rate_limit(request: Request, action: str) -> None:
    """Enforce brute-force rate limit by client IP and action."""
    client_ip = get_client_ip(request)
    key = f"{client_ip}:{action}"
    if not auth_rate_limiter.is_allowed(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again in 15 minutes.",
        )


def check_csrf(request: Request) -> None:
    """Validate double-submit CSRF token for cookie-authenticated requests."""
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if session_cookie:  # Only enforce CSRF when authenticated via cookies
        cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
        header_csrf = request.headers.get(CSRF_HEADER_NAME)
        if not cookie_csrf or not header_csrf or not verify_csrf_token(header_csrf, cookie_csrf):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed. Include a valid X-CSRF-Token header.",
            )


def get_current_user(request: Request) -> dict:
    """FastAPI dependency: Authenticates user from HttpOnly session cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    sess = validate_session(token)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please sign in again.",
        )
    user = auth_store.get_user_by_id(sess["user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
        )
    return user


def set_auth_cookies(response: Response, token: str, csrf_token: str) -> None:
    """Set secure session and CSRF cookies."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=get_cookie_secure(),
        samesite=get_cookie_samesite(),
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=False,  # JavaScript reads this to attach X-CSRF-Token header
        secure=get_cookie_secure(),
        samesite=get_cookie_samesite(),
        path="/",
    )
    response.headers[CSRF_HEADER_NAME] = csrf_token


def clear_auth_cookies(response: Response) -> None:
    """Clear session and CSRF cookies on logout."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=get_cookie_secure(),
        samesite=get_cookie_samesite(),
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        secure=get_cookie_secure(),
        samesite=get_cookie_samesite(),
    )


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def register(body: RegisterRequest, request: Request, response: Response):
    enforce_rate_limit(request, "register")

    password_hash = hash_password(body.password)
    user = auth_store.create_user(body.email, password_hash, body.name or "")
    if not user:
        # Avoid leaking duplicate email information directly while rejecting duplicates
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to complete registration. If you already have an account, please sign in.",
        )

    # Automatically establish a session upon successful registration
    token, _ = create_session(
        user["id"],
        user_agent=request.headers.get("user-agent"),
        ip_address=get_client_ip(request),
    )
    csrf_token = generate_csrf_token()
    set_auth_cookies(response, token, csrf_token)

    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        created_at=user["created_at"],
    )


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)
    enforce_rate_limit(request, "login")

    user = auth_store.get_user_by_email_with_hash(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        auth_rate_limiter.record_attempt(f"{client_ip}:login")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_FAILED_MESSAGE,
        )

    # Reset rate limit counter on successful credentials
    auth_rate_limiter.reset(f"{client_ip}:login")

    token, _ = create_session(
        user["id"],
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip,
    )
    csrf_token = generate_csrf_token()
    set_auth_cookies(response, token, csrf_token)

    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        created_at=user["created_at"],
    )


@router.post("/logout")
def logout(request: Request, response: Response):
    # Enforce CSRF check for state-changing logout requests
    check_csrf(request)

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        revoke_session(token)

    clear_auth_cookies(response)
    return {"message": "Logged out successfully."}


@router.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        created_at=user["created_at"],
    )


@router.post("/forgot-password", response_model=AuthMessageResponse)
def forgot_password(body: ForgotPasswordRequest, request: Request):
    enforce_rate_limit(request, "forgot")

    dev_token = None
    user = auth_store.get_user_by_email_with_hash(body.email)
    if user:
        token = create_password_reset_token(user["id"])
        # Deliver to local test sink in non-production
        from .email_sink import dev_email_sink, is_production
        if not is_production():
            dev_email_sink.deliver_reset_token(user["email"], token)
            # Only populate dev_reset_token if explicitly permitted and NOT in production
            if os.environ.get("AGENTRELIABILITY_EXPOSE_DEV_RESET_TOKEN", "false").lower() in ("true", "1"):
                dev_token = token
        # Safe log without secret token exposure
        logger.info("Password reset requested for user id=%d (token dispatched to sink)", user["id"])

    # Always return identical response whether or not user exists
    return AuthMessageResponse(
        message=RESET_SENT_MESSAGE,
        dev_reset_token=dev_token,
    )


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest):
    user_id = validate_password_reset_token(body.token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token is invalid, expired, or has already been used.",
        )

    # Hash new password with scrypt
    new_hash = hash_password(body.new_password)
    auth_store.update_user_password(user_id, new_hash)

    # Invalidate the token (single-use enforcement)
    consume_password_reset_token(body.token)

    # Invalidate all active sessions for this account
    revoke_all_user_sessions(user_id)

    return {"message": "Password has been successfully reset. Please sign in with your new password."}

