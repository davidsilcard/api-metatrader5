from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI

from .api.routes.health import router as health_router
from .api.routes.orders import router as orders_router
from .api.routes.quotes import router as quotes_router
from .api.routes.symbols import router as symbols_router
from .core.config import Settings, get_settings
from .core.errors import register_exception_handlers
from .core.logging import configure_logging
from .services.market_data import MarketDataService
from .services.mt5_client import MetaTrader5Client
from .services.order_service import OrderService


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    mt5_client = MetaTrader5Client(settings=settings)
    market_data_service = MarketDataService(settings=settings, client=mt5_client)
    order_service = OrderService(
        settings=settings,
        client=mt5_client,
        market_data_service=market_data_service,
    )

    app = FastAPI(
        title="api-metatrader5",
        version=settings.app_version,
    )
    app.state.settings = settings
    app.state.mt5_client = mt5_client
    app.state.market_data_service = market_data_service
    app.state.order_service = order_service

    register_exception_handlers(app)
    _register_request_logging(app)

    app.include_router(health_router)
    app.include_router(quotes_router)
    app.include_router(symbols_router)
    app.include_router(orders_router)

    @app.on_event("shutdown")
    def _shutdown_mt5() -> None:
        mt5_client.shutdown()

    return app


def create_test_app(*, settings: Settings, mt5_client) -> FastAPI:
    configure_logging(settings)
    market_data_service = MarketDataService(settings=settings, client=mt5_client)
    order_service = OrderService(
        settings=settings,
        client=mt5_client,
        market_data_service=market_data_service,
    )

    app = FastAPI(
        title="api-metatrader5",
        version=settings.app_version,
    )
    app.state.settings = settings
    app.state.mt5_client = mt5_client
    app.state.market_data_service = market_data_service
    app.state.order_service = order_service

    register_exception_handlers(app)
    _register_request_logging(app)

    app.include_router(health_router)
    app.include_router(quotes_router)
    app.include_router(symbols_router)
    app.include_router(orders_router)
    return app


def _register_request_logging(app: FastAPI) -> None:
    logger = logging.getLogger("api_metatrader5.request")

    @app.middleware("http")
    async def _request_logging(request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        auth = getattr(request.state, "hmac_auth", None)
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%s key_id=%s client=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            getattr(auth, "key_id", "-"),
            getattr(request.client, "host", "-"),
        )
        response.headers["X-Request-Id"] = request_id
        return response
