from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_market_data_service, get_settings
from ...core.config import Settings
from ...services.market_data import MarketDataService


router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
    }


@router.get("/ready")
def ready(
    market_data_service: MarketDataService = Depends(get_market_data_service),
) -> dict[str, object]:
    return market_data_service.readiness()
