from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QuoteResponse(BaseModel):
    requested_symbol: str
    symbol: str
    description: str | None = None
    path: str | None = None
    currency_base: str | None = None
    currency_profit: str | None = None
    currency_margin: str | None = None
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: int | None = None
    volume_real: float | None = None
    digits: int | None = None
    point: float | None = None
    spread: int | None = None
    spread_float: bool | None = None
    visible: bool | None = None
    trade_mode: int | None = None
    time_utc: datetime | None = None
    time_msc: int | None = None
    raw_tick: dict[str, Any] | None = None
    raw_symbol: dict[str, Any] | None = None
    source: str = "metatrader5"


class BatchQuoteRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=100)
    include_raw: bool = True


class BatchQuoteError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class BatchQuoteItem(BaseModel):
    requested_symbol: str
    ok: bool
    quote: QuoteResponse | None = None
    error: BatchQuoteError | None = None


class BatchQuoteResponse(BaseModel):
    items: list[BatchQuoteItem]
    count_total: int
    count_success: int
    count_error: int


class SymbolSearchItem(BaseModel):
    requested_query: str
    symbol: str
    description: str | None = None
    path: str | None = None
    currency_base: str | None = None
    currency_profit: str | None = None
    digits: int | None = None
    visible: bool | None = None
    trade_mode: int | None = None


class SymbolSearchResponse(BaseModel):
    query: str
    count: int
    items: list[SymbolSearchItem]
