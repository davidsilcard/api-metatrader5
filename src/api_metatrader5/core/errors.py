from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthorized"


class AuthorizationError(AppError):
    status_code = 403
    code = "forbidden"


class SymbolNotFoundError(AppError):
    status_code = 404
    code = "symbol_not_found"


class MarketDataUnavailableError(AppError):
    status_code = 503
    code = "market_data_unavailable"


class Mt5ConnectionError(AppError):
    status_code = 503
    code = "mt5_connection_error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_server_error",
                    "message": "Unexpected server error.",
                    "details": {"exception_type": exc.__class__.__name__},
                }
            },
        )
