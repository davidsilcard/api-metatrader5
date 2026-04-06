from __future__ import annotations

from fastapi import Request

from ..core.config import Settings
from ..services.market_data import MarketDataService
from ..services.order_service import OrderService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_market_data_service(request: Request) -> MarketDataService:
    return request.app.state.market_data_service


def get_order_service(request: Request) -> OrderService:
    return request.app.state.order_service
