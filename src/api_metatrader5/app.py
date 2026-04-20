from __future__ import annotations

import logging
import os
import time
import uuid

from fastapi import FastAPI

from .api.routes.health import router as health_router
from .api.routes.metrics import router as metrics_router
from .api.routes.orders import router as orders_router
from .api.routes.quotes import router as quotes_router
from .api.routes.symbols import router as symbols_router
from .core.config import Settings, get_settings
from .core.errors import register_exception_handlers
from .core.logging import configure_logging
from .services.btg_trader_desk_client import BtgTraderDeskClient
from .services.market_data import MarketDataService
from .services.monitoring import MonitoringService
from .services.order_service import OrderService


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    logger = logging.getLogger("api_metatrader5.app")
    market_data_client = BtgTraderDeskClient(settings=settings)
    market_data_service = MarketDataService(settings=settings, client=market_data_client)
    monitoring_service = MonitoringService(market_data_client=market_data_client)
    order_service = OrderService(settings=settings)

    app = FastAPI(
        title="api-metatrader5",
        version=settings.app_version,
    )
    app.state.settings = settings
    app.state.market_data_client = market_data_client
    app.state.market_data_service = market_data_service
    app.state.monitoring_service = monitoring_service
    app.state.order_service = order_service

    logger.info(
        "app_started pid=%s cwd=%s app_file=%s host=%s port=%s version=%s",
        os.getpid(),
        os.getcwd(),
        __file__,
        settings.app_host,
        settings.app_port,
        settings.app_version,
    )

    register_exception_handlers(app)
    _register_request_logging(app)

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(quotes_router)
    app.include_router(symbols_router)
    app.include_router(orders_router)

    @app.on_event("shutdown")
    def _shutdown_market_data() -> None:
        market_data_client.shutdown()

    return app


def create_test_app(*, settings: Settings, market_data_client=None, mt5_client=None) -> FastAPI:
    configure_logging(settings)
    market_data_client = market_data_client or mt5_client
    if market_data_client is None:
        raise ValueError("Provide market_data_client or mt5_client to create_test_app().")
    market_data_service = MarketDataService(settings=settings, client=market_data_client)
    monitoring_service = MonitoringService(market_data_client=market_data_client)
    order_service = OrderService(settings=settings)

    app = FastAPI(
        title="api-metatrader5",
        version=settings.app_version,
    )
    app.state.settings = settings
    app.state.market_data_client = market_data_client
    app.state.market_data_service = market_data_service
    app.state.monitoring_service = monitoring_service
    app.state.order_service = order_service

    register_exception_handlers(app)
    _register_request_logging(app)

    app.include_router(health_router)
    app.include_router(metrics_router)
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
        endpoint_key = f"{request.method} {request.url.path}"
        app.state.monitoring_service.request_started(endpoint_key)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            app.state.monitoring_service.request_finished(
                endpoint_key,
                status_code=500,
                duration_ms=elapsed_ms,
            )
            raise

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        app.state.monitoring_service.request_finished(
            endpoint_key,
            status_code=response.status_code,
            duration_ms=elapsed_ms,
        )
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
        response.headers["X-App-Version"] = app.state.settings.app_version
        response.headers["X-App-Pid"] = str(os.getpid())
        return response
