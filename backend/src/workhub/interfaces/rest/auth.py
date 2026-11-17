"""Routes d'authentification des utilisateurs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from workhub.iam.api import (
    AuthResult,
    AuthService,
    UserView,
    get_auth_service,
    get_cookie_settings,
)
from workhub.shared.api import AuthenticationError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """Identifiants de connexion."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    """Compte exposé après authentification."""

    id: UUID
    email: str
    display_name: str
    is_admin: bool
    last_login_at: datetime | None

    @classmethod
    def from_view(cls, user: UserView) -> UserResponse:
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=user.is_admin,
            last_login_at=user.last_login_at,
        )


class TokenResponse(BaseModel):
    """Jeton d'accès ; le refresh token reste exclusivement dans le cookie."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserResponse


def _token_response(result: AuthResult, service: AuthService) -> JSONResponse:
    body = TokenResponse(
        access_token=result.access_token,
        expires_in=service.access_token_ttl_seconds,
        user=UserResponse.from_view(result.user),
    )
    response = JSONResponse(content=body.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    cookie = get_cookie_settings()
    response.set_cookie(
        key=cookie.name,
        value=result.refresh_token,
        max_age=service.refresh_token_ttl_seconds,
        path=cookie.path,
        secure=cookie.secure,
        httponly=True,
        samesite="strict",
    )
    return response


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> JSONResponse:
    """Vérifie les identifiants et ouvre une session."""
    result = await service.login(payload.email, payload.password)
    return _token_response(result, service)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> JSONResponse:
    """Fait tourner le refresh token et renvoie un nouvel accès."""
    cookie = get_cookie_settings()
    token = request.cookies.get(cookie.name)
    if not token:
        raise AuthenticationError("Refresh token absent")
    result = await service.refresh(token)
    return _token_response(result, service)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    """Révoque la session et efface le cookie de rafraîchissement."""
    cookie = get_cookie_settings()
    token = request.cookies.get(cookie.name)
    if token:
        await service.logout(token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(
        key=cookie.name,
        path=cookie.path,
        secure=cookie.secure,
        httponly=True,
        samesite="strict",
    )
    return response


@router.get("/me", response_model=UserResponse)
async def me(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> JSONResponse:
    """Retourne le compte associé au JWT d'accès."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Jeton d'accès absent")
    user = await service.authenticate(credentials.credentials)
    body = UserResponse.from_view(user)
    response = JSONResponse(content=body.model_dump(mode="json"))
    response.headers["Cache-Control"] = "no-store"
    return response
