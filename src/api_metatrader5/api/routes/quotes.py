from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_market_data_service, get_settings
from ...core.config import Settings
from ...schemas.market import BatchQuoteRequest, BatchQuoteResponse, QuoteResponse
from ...security.hmac_auth import verify_hmac_request
from ...services.market_data import MarketDataService


router = APIRouter(
    prefix="/internal/v1/quotes",
    tags=["quotes"],
    dependencies=[Depends(verify_hmac_request)],
)


@router.get("/{symbol}", response_model=QuoteResponse)
def get_quote(
    symbol: str,
    include_raw: bool = Query(True),
    _settings: Settings = Depends(get_settings),
    market_data_service: MarketDataService = Depends(get_market_data_service),
) -> QuoteResponse:
    return market_data_service.get_quote(symbol=symbol, include_raw=include_raw)


@router.post("/batch", response_model=BatchQuoteResponse)
def get_quotes_batch(
    payload: BatchQuoteRequest,
    _settings: Settings = Depends(get_settings),
    market_data_service: MarketDataService = Depends(get_market_data_service),
) -> BatchQuoteResponse:
    items = [
        market_data_service.get_quote(symbol=symbol, include_raw=payload.include_raw)
        for symbol in payload.symbols
    ]
    return BatchQuoteResponse(items=items, count=len(items))
