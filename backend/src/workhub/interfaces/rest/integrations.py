"""Routes de gestion des intégrations et de leurs jetons."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from workhub.iam.api import (
    CreatedIntegrationView,
    IntegrationService,
    IntegrationView,
    IssuedApiTokenView,
    Principal,
    get_integration_service,
)
from workhub.interfaces.rest.dependencies import current_principal
from workhub.interfaces.rest.middleware import get_request_id

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

IntegrationKindValue = Literal["opencode", "claude_code", "codex", "other"]


class IntegrationResponse(BaseModel):
    """Intégration exposée, sans secret."""

    id: UUID
    name: str
    kind: str
    owner_id: UUID
    created_at: datetime
    revoked_at: datetime | None

    @classmethod
    def from_view(cls, integration: IntegrationView) -> IntegrationResponse:
        return cls(
            id=integration.id,
            name=integration.name,
            kind=integration.kind,
            owner_id=integration.owner_id,
            created_at=integration.created_at,
            revoked_at=integration.revoked_at,
        )


class IssuedTokenResponse(BaseModel):
    """Jeton brut ; il ne sera plus jamais affiché après cette réponse."""

    id: UUID
    token: str
    scopes: list[str]
    expires_at: datetime | None

    @classmethod
    def from_view(cls, token: IssuedApiTokenView) -> IssuedTokenResponse:
        return cls(
            id=token.id,
            token=token.token,
            scopes=sorted(token.scopes),
            expires_at=token.expires_at,
        )


class CreatedIntegrationResponse(BaseModel):
    """Intégration créée et son premier jeton."""

    integration: IntegrationResponse
    token: IssuedTokenResponse

    @classmethod
    def from_view(cls, created: CreatedIntegrationView) -> CreatedIntegrationResponse:
        return cls(
            integration=IntegrationResponse.from_view(created.integration),
            token=IssuedTokenResponse.from_view(created.token),
        )


class CreateIntegrationRequest(BaseModel):
    """Paramètres de création d'une intégration et de son premier jeton."""

    name: str = Field(min_length=1, max_length=200)
    kind: IntegrationKindValue
    scopes: list[str] = Field(min_length=1, max_length=50)
    expires_at: datetime | None = None


class CreateTokenRequest(BaseModel):
    """Paramètres d'émission d'un jeton supplémentaire."""

    scopes: list[str] = Field(min_length=1, max_length=50)
    expires_at: datetime | None = None


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post(
    "",
    response_model=CreatedIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    payload: CreateIntegrationRequest,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> JSONResponse:
    """Crée une intégration et retourne son jeton brut une seule fois."""
    created = await service.create(
        principal,
        name=payload.name,
        kind=payload.kind,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
        request_id=get_request_id(request),
    )
    body = CreatedIntegrationResponse.from_view(created)
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        headers={"Cache-Control": "no-store"},
    )


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> list[IntegrationResponse]:
    """Liste les intégrations du principal."""
    return [IntegrationResponse.from_view(item) for item in await service.list(principal)]


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_integration(
    integration_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> Response:
    """Révoque l'intégration et tous ses jetons."""
    await service.revoke(principal, integration_id, request_id=get_request_id(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{integration_id}/tokens",
    response_model=IssuedTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_token(
    integration_id: UUID,
    payload: CreateTokenRequest,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[IntegrationService, Depends(get_integration_service)],
    response: Response,
) -> IssuedTokenResponse:
    """Émet un jeton supplémentaire pour une intégration active."""
    issued = await service.create_token(
        principal,
        integration_id,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
        request_id=get_request_id(request),
    )
    _no_store(response)
    return IssuedTokenResponse.from_view(issued)


@router.delete(
    "/{integration_id}/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_token(
    integration_id: UUID,
    token_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[IntegrationService, Depends(get_integration_service)],
) -> Response:
    """Révoque un jeton précis."""
    await service.revoke_token(
        principal,
        integration_id,
        token_id,
        request_id=get_request_id(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
