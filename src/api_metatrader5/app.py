from __future__ import annotations

from fastapi import FastAPI

from .api.routes.health import router as health_router
from .api.routes.orders import router as orders_router
from .api.routes.quotes import router as quotes_router
from .api.routes.symbols import router as symbols_router
from .core.config import Settings, get_settings
from .core.errors import register_exception_handlers
from .services.market_data import MarketDataService
from .services.mt5_client import MetaTrader5Client
from .services.order_service import OrderService


def create_app() -> FastAPI:
    settings = get_settings()
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

    app.include_router(health_router)
    app.include_router(quotes_router)
    app.include_router(symbols_router)
    app.include_router(orders_router)

    @app.on_event("shutdown")
    def _shutdown_mt5() -> None:
        mt5_client.shutdown()

    return app


def create_test_app(*, settings: Settings, mt5_client) -> FastAPI:
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

    app.include_router(health_router)
    app.include_router(quotes_router)
    app.include_router(symbols_router)
    app.include_router(orders_router)
    return app
