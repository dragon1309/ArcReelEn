"""
Authentication API routes.

Provides OAuth2 login and token verification endpoints.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from server.auth import CurrentUser, check_credentials, create_token

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Response Models ====================


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class VerifyResponse(BaseModel):
    valid: bool
    username: str


# ==================== Routes ====================


@router.post("/auth/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    """Authenticate a user and return an access token.

    Uses the standard OAuth2 password form and returns an
    ``access_token`` on success.
    """
    if not check_credentials(form_data.username, form_data.password):
        logger.warning("Login failed: invalid username or password (user: %s)", form_data.username)
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token(form_data.username)
    logger.info("User login succeeded: %s", form_data.username)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get("/auth/verify", response_model=VerifyResponse)
async def verify(
    current_user: CurrentUser,
):
    """Verify that the current bearer token is valid."""
    return VerifyResponse(valid=True, username=current_user.sub)
