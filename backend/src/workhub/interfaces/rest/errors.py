"""Enveloppe d'erreur commune à l'API REST.

Le domaine produit des `WorkHubError` sans connaître HTTP. Ce module les traduit en une
réponse JSON stable : `{"error": {"code", "message", "details", "request_id"}}`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from workhub.shared.api import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    PreconditionFailedError,
    RateLimitedError,
    ValidationError,
    WorkHubError,
)


class ApiErrorBody(BaseModel):
    """Corps d'une erreur API."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ApiErrorResponse(BaseModel):
    """Enveloppe unique des erreurs REST."""

    error: ApiErrorBody


_STATUS_BY_ERROR: tuple[tuple[type[WorkHubError], int], ...] = (
    (ValidationError, 422),
    (AuthenticationError, 401),
    (PermissionDeniedError, 403),
    (NotFoundError, 404),
    (ConflictError, 409),
    (PreconditionFailedError, 412),
    (RateLimitedError, 429),
)

_DEFAULT_STATUS = 500


def status_for(error: WorkHubError) -> int:
    """Traduit une erreur métier en statut HTTP."""
    for error_type, status in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return status
    return _DEFAULT_STATUS


def _json_response(status: int, body: ApiErrorResponse) -> JSONResponse:
    return JSONResponse(status_code=status, content=body.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    """Enregistre les gestionnaires d'erreurs communs sur l'application."""

    @app.exception_handler(WorkHubError)
    async def _handle_workhub_error(_: Request, exc: WorkHubError) -> JSONResponse:
        body = ApiErrorResponse(
            error=ApiErrorBody(
                code=exc.code,
                message=exc.message,
                details=dict(exc.details),
            )
        )
        return _json_response(status_for(exc), body)

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        body = ApiErrorResponse(
            error=ApiErrorBody(
                code=ValidationError.code,
                message="Requête invalide",
                details={"errors": jsonable_encoder(exc.errors())},
            )
        )
        return _json_response(422, body)
