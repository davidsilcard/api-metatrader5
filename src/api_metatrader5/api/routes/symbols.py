from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_market_data_service, get_settings
from ...core.config import Settings
from ...schemas.market import SymbolSearchResponse
from ...security.hmac_auth import require_hmac_scopes
from ...services.market_data import MarketDataService


router = APIRouter(
    prefix="/internal/v1/symbols",
    tags=["symbols"],
    dependencies=[Depends(require_hmac_scopes("symbols:read"))],
)


@router.get("/search", response_model=SymbolSearchResponse)
def search_symbols(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    _settings: Settings = Depends(get_settings),
    market_data_service: MarketDataService = Depends(get_market_data_service),
) -> SymbolSearchResponse:
    items = market_data_service.search_symbols(query=q, limit=limit)
    return SymbolSearchResponse(query=q, count=len(items), items=items)
