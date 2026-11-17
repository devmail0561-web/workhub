"""Enveloppe d'erreur commune à l'API REST.

Le domaine produit des `WorkHubError` sans connaître HTTP. Ce module les traduit en une
réponse JSON stable : `{"error": {"code", "message", "details", "request_id"}}`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from workhub.interfaces.rest.middleware import REQUEST_ID_HEADER, get_request_id
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


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiErrorResponse, "description": "Authentification requise"},
    404: {"model": ApiErrorResponse, "description": "Ressource introuvable"},
    405: {"model": ApiErrorResponse, "description": "Méthode non autorisée"},
    500: {"model": ApiErrorResponse, "description": "Erreur interne"},
}


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

_HTTP_ERROR_CODES = {
    400: "validation_error",
    401: "authentication_required",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    412: "precondition_failed",
    422: "validation_error",
    429: "rate_limited",
}

_HTTP_ERROR_MESSAGES = {
    400: "Requête invalide",
    401: "Authentification requise",
    403: "Accès refusé",
    404: "Ressource introuvable",
    405: "Méthode non autorisée",
    409: "Conflit",
    412: "Précondition invalide",
    422: "Requête invalide",
    429: "Trop de requêtes",
}


def status_for(error: WorkHubError) -> int:
    """Traduit une erreur métier en statut HTTP."""
    for error_type, status in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return status
    return _DEFAULT_STATUS


def _headers(
    request_id: str | None,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    headers = dict(extra or {})
    if request_id is not None:
        headers[REQUEST_ID_HEADER] = request_id
    return headers


def _json_response(
    status: int,
    body: ApiErrorResponse,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def _validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    return [
        {
            "type": error["type"],
            "loc": jsonable_encoder(error["loc"]),
            "msg": error["msg"],
        }
        for error in exc.errors()
    ]


def install_error_handlers(app: FastAPI) -> None:
    """Enregistre les gestionnaires d'erreurs communs sur l'application."""

    @app.exception_handler(WorkHubError)
    async def _handle_workhub_error(request: Request, exc: WorkHubError) -> JSONResponse:
        request_id = get_request_id(request)
        body = ApiErrorResponse(
            error=ApiErrorBody(
                code=exc.code,
                message=exc.message,
                details=dict(exc.details),
                request_id=request_id,
            )
        )
        status = status_for(exc)
        headers = _headers(request_id)
        if isinstance(exc, AuthenticationError):
            headers["WWW-Authenticate"] = "Bearer"
        return _json_response(status, body, headers=headers)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = exc.status_code
        request_id = get_request_id(request)
        is_server_error = status >= 500
        code = "internal_error" if is_server_error else _HTTP_ERROR_CODES.get(status, "http_error")
        message = (
            "Erreur interne"
            if is_server_error
            else _HTTP_ERROR_MESSAGES.get(status, str(exc.detail))
        )
        body = ApiErrorResponse(
            error=ApiErrorBody(
                code=code,
                message=message,
                details={},
                request_id=request_id,
            )
        )
        return _json_response(status, body, headers=_headers(request_id, exc.headers))

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = get_request_id(request)
        body = ApiErrorResponse(
            error=ApiErrorBody(
                code=ValidationError.code,
                message="Requête invalide",
                details={"errors": _validation_errors(exc)},
                request_id=request_id,
            )
        )
        return _json_response(422, body, headers=_headers(request_id))

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, _: Exception) -> JSONResponse:
        request_id = get_request_id(request)
        body = ApiErrorResponse(
            error=ApiErrorBody(
                code=WorkHubError.code,
                message="Erreur interne",
                details={},
                request_id=request_id,
            )
        )
        return _json_response(500, body, headers=_headers(request_id))
