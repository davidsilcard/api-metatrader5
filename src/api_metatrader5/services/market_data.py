from __future__ import annotations

from datetime import UTC, datetime
import logging
import threading
import time
from typing import Any

from ..core.config import Settings
from ..core.errors import AppError, MarketDataUnavailableError, ProviderTimeoutError, SymbolNotFoundError
from ..schemas.market import BatchQuoteItem, BatchQuoteResponse, QuoteResponse, SymbolSearchItem
from .market_data_client import MarketDataClientProtocol


logger = logging.getLogger(__name__)


class MarketDataService:
    def __init__(self, *, settings: Settings, client: MarketDataClientProtocol) -> None:
        self.settings = settings
        self.client = client
        self._quote_cache_lock = threading.Lock()
        self._quote_cache: dict[tuple[str, bool], tuple[float, QuoteResponse]] = {}
        self._negative_cache: dict[tuple[str, bool], tuple[float, AppError]] = {}
        self._inflight_lock = threading.Lock()
        self._inflight_quotes: dict[tuple[str, bool], _InflightQuote] = {}

    def readiness(self) -> dict[str, Any]:
        try:
            self.client.ensure_connected()
        except Exception as exc:
            return {
                "status": "not_ready",
                "provider": "btg_trader_desk",
                "connected": False,
                "state": "error",
                "mt5_connected": False,
                "mt5_state": "error",
                "details": {
                    "exception_type": exc.__class__.__name__,
                    "message": str(exc),
                },
            }

        status = self.client.connection_status()
        return {
            "status": "ready",
            "provider": status.get("provider", "btg_trader_desk"),
            "connected": bool(status.get("connected")),
            "state": status.get("state", "connected"),
            "mt5_connected": bool(status.get("connected")),
            "mt5_state": status.get("state", "connected"),
            "reconnect_count": status.get("reconnect_count", 0),
            "last_connected_at": status.get("last_connected_at"),
            "last_error": status.get("last_error"),
        }

    def get_quote(self, *, symbol: str, include_raw: bool = True) -> QuoteResponse:
        requested_symbol = self._normalize_symbol(symbol)
        started = time.perf_counter()
        logger.info(
            "quote_start symbol=%s include_raw=%s",
            requested_symbol,
            include_raw,
        )
        cached = self._get_cached_quote(requested_symbol, include_raw)
        if cached is not None:
            logger.info(
                "quote_cache_hit symbol=%s duration_ms=%s",
                requested_symbol,
                round((time.perf_counter() - started) * 1000, 2),
            )
            return cached
        cached_error = self._get_cached_negative_quote(requested_symbol, include_raw)
        if cached_error is not None:
            logger.info(
                "quote_negative_cache_hit symbol=%s code=%s duration_ms=%s",
                requested_symbol,
                cached_error.code,
                round((time.perf_counter() - started) * 1000, 2),
            )
            raise cached_error

        inflight, owner = self._acquire_inflight(requested_symbol, include_raw)
        if not owner:
            wait_timeout = self._inflight_wait_timeout_seconds()
            logger.info(
                "quote_inflight_wait symbol=%s timeout_seconds=%s",
                requested_symbol,
                wait_timeout,
            )
            completed = inflight.event.wait(timeout=wait_timeout)
            if not completed:
                timeout_error = ProviderTimeoutError(
                    "Provider timeout",
                    details={"symbol": requested_symbol, "stage": "inflight_wait"},
                )
                self._store_negative_quote(requested_symbol, include_raw, timeout_error)
                self._drop_stale_inflight(requested_symbol, include_raw, inflight)
                logger.warning(
                    "quote_inflight_wait_timeout symbol=%s timeout_seconds=%s",
                    requested_symbol,
                    wait_timeout,
                )
                raise timeout_error
            if inflight.error is not None:
                raise inflight.error
            if inflight.quote is not None:
                return inflight.quote
            raise MarketDataUnavailableError(
                "No tick data available for symbol.",
                details={"symbol": requested_symbol},
            )

        resolved_symbol, symbol_info = self._resolve_symbol_info(requested_symbol)
        try:
            tick_info = self._get_tick_with_select_retry(resolved_symbol)
            if not tick_info:
                raise MarketDataUnavailableError(
                    "No tick data available for symbol.",
                    details={"symbol": resolved_symbol},
                )

            time_utc = self._tick_timestamp(tick_info)
            quote = QuoteResponse(
                requested_symbol=requested_symbol,
                symbol=resolved_symbol,
                description=self._as_text(symbol_info.get("description")),
                path=self._as_text(symbol_info.get("path")),
                currency_base=self._as_text(symbol_info.get("currency_base")),
                currency_profit=self._as_text(symbol_info.get("currency_profit")),
                currency_margin=self._as_text(symbol_info.get("currency_margin")),
                bid=self._as_float(tick_info.get("bid")),
                ask=self._as_float(tick_info.get("ask")),
                last=self._as_float(tick_info.get("last")),
                volume=self._as_int(tick_info.get("volume")),
                volume_real=self._as_float(tick_info.get("volume_real")),
                digits=self._as_int(symbol_info.get("digits")),
                point=self._as_float(symbol_info.get("point")),
                spread=self._as_int(symbol_info.get("spread")),
                spread_float=self._as_bool(symbol_info.get("spread_float")),
                visible=self._as_bool(symbol_info.get("visible")),
                trade_mode=self._as_int(symbol_info.get("trade_mode")),
                time_utc=time_utc,
                time_msc=self._as_int(tick_info.get("time_msc")),
                raw_tick=tick_info if include_raw else None,
                raw_symbol=symbol_info if include_raw else None,
                source="btg-trader-desk",
            )
            self._store_cached_quote(requested_symbol, include_raw, quote)
            inflight.quote = quote
            logger.info(
                "quote_success symbol=%s resolved_symbol=%s duration_ms=%s",
                requested_symbol,
                resolved_symbol,
                round((time.perf_counter() - started) * 1000, 2),
            )
            return quote
        except Exception as exc:
            if isinstance(exc, AppError):
                if isinstance(exc, ProviderTimeoutError):
                    self._store_negative_quote(requested_symbol, include_raw, exc)
                inflight.error = exc
            logger.warning(
                "quote_error symbol=%s error_type=%s message=%s duration_ms=%s",
                requested_symbol,
                exc.__class__.__name__,
                str(exc),
                round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        finally:
            self._release_inflight(requested_symbol, include_raw, inflight)

    def search_symbols(self, *, query: str, limit: int) -> list[SymbolSearchItem]:
        normalized = self._normalize_symbol(query)
        pattern = f"*{normalized}*"
        rows = self.client.symbols_get(group=pattern)
        rows = sorted(
            rows,
            key=lambda item: (
                item.get("name", "").upper() != normalized,
                not item.get("name", "").upper().startswith(normalized),
                item.get("name", ""),
            ),
        )
        items: list[SymbolSearchItem] = []
        for row in rows[:limit]:
            items.append(
                SymbolSearchItem(
                    requested_query=normalized,
                    symbol=self._as_text(row.get("name")) or "",
                    description=self._as_text(row.get("description")),
                    path=self._as_text(row.get("path")),
                    currency_base=self._as_text(row.get("currency_base")),
                    currency_profit=self._as_text(row.get("currency_profit")),
                    digits=self._as_int(row.get("digits")),
                    visible=self._as_bool(row.get("visible")),
                    trade_mode=self._as_int(row.get("trade_mode")),
                )
            )
        return items

    def get_quotes_batch(self, *, symbols: list[str], include_raw: bool) -> BatchQuoteResponse:
        started = time.perf_counter()
        logger.info(
            "batch_start count=%s include_raw=%s symbols=%s",
            len(symbols),
            include_raw,
            ",".join(self._normalize_symbol(symbol) for symbol in symbols),
        )
        items: list[BatchQuoteItem] = []
        success_count = 0
        error_count = 0
        resolved_items: dict[str, QuoteResponse | AppError] = {}
        for symbol in symbols:
            requested_symbol = self._normalize_symbol(symbol)
            cached_result = resolved_items.get(requested_symbol)
            if isinstance(cached_result, QuoteResponse):
                quote = cached_result
            elif isinstance(cached_result, AppError):
                exc = cached_result
                error_count += 1
                items.append(
                    BatchQuoteItem(
                        requested_symbol=requested_symbol,
                        ok=False,
                        quote=None,
                        error={
                            "code": exc.code,
                            "message": exc.message,
                            "details": exc.details,
                        },
                    )
                )
                continue
            else:
                item_started = time.perf_counter()
                try:
                    quote = self.get_quote(symbol=symbol, include_raw=include_raw)
                    resolved_items[requested_symbol] = quote
                    logger.info(
                        "batch_item_success symbol=%s duration_ms=%s",
                        requested_symbol,
                        round((time.perf_counter() - item_started) * 1000, 2),
                    )
                except AppError as exc:
                    resolved_items[requested_symbol] = exc
                    if isinstance(exc, ProviderTimeoutError):
                        logger.warning(
                            "Batch quote item timed out.",
                            extra={"symbol": requested_symbol},
                        )
                    logger.warning(
                        "batch_item_error symbol=%s code=%s duration_ms=%s",
                        requested_symbol,
                        exc.code,
                        round((time.perf_counter() - item_started) * 1000, 2),
                    )
                    error_count += 1
                    items.append(
                        BatchQuoteItem(
                            requested_symbol=requested_symbol,
                            ok=False,
                            quote=None,
                            error={
                                "code": exc.code,
                                "message": exc.message,
                                "details": exc.details,
                            },
                        )
                    )
                    continue

            success_count += 1
            items.append(
                BatchQuoteItem(
                    requested_symbol=requested_symbol,
                    ok=True,
                    quote=quote,
                    error=None,
                )
            )

        response = BatchQuoteResponse(
            items=items,
            count_total=len(items),
            count_success=success_count,
            count_error=error_count,
            partial=success_count > 0 and error_count > 0,
        )
        logger.info(
            "batch_finished count_total=%s count_success=%s count_error=%s partial=%s duration_ms=%s",
            response.count_total,
            response.count_success,
            response.count_error,
            response.partial,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return response

    def resolve_symbol_name(self, symbol: str) -> str:
        requested_symbol = self._normalize_symbol(symbol)
        resolved, _info = self._resolve_symbol_info(requested_symbol)
        return resolved

    def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        _resolved_symbol, symbol_info = self._resolve_symbol_info(self._normalize_symbol(symbol))
        return symbol_info

    def _resolve_symbol_info(self, requested_symbol: str) -> tuple[str, dict[str, Any]]:
        candidates = [requested_symbol]
        alias = self.settings.symbol_alias_map.get(requested_symbol)
        if alias and alias not in candidates:
            candidates.insert(0, alias)

        for candidate in candidates:
            symbol_info = self.client.symbol_info(candidate)
            if symbol_info:
                return candidate, symbol_info
            self.client.symbol_select(candidate, True)
            symbol_info = self.client.symbol_info(candidate)
            if symbol_info:
                return candidate, symbol_info

        matches = self.client.symbols_get(group=f"*{requested_symbol}*")
        if matches:
            best = matches[0]
            resolved_symbol = self._as_text(best.get("name"))
            if resolved_symbol:
                self.client.symbol_select(resolved_symbol, True)
                symbol_info = self.client.symbol_info(resolved_symbol)
                if symbol_info:
                    return resolved_symbol, symbol_info

        raise SymbolNotFoundError(
            "Symbol not found in configured market data provider.",
            details={"symbol": requested_symbol},
        )

    def _get_tick_with_select_retry(self, symbol: str) -> dict[str, Any] | None:
        tick_info = self.client.symbol_info_tick(symbol)
        if tick_info and self._has_meaningful_tick(tick_info):
            return tick_info

        self.client.symbol_select(symbol, True)
        tick_info = self.client.symbol_info_tick(symbol)
        if tick_info and self._has_meaningful_tick(tick_info):
            return tick_info
        return None

    def _get_cached_quote(self, symbol: str, include_raw: bool) -> QuoteResponse | None:
        ttl_ms = max(0, int(self.settings.quote_cache_ttl_ms))
        if ttl_ms <= 0:
            return None
        now = time.monotonic()
        cache_key = (symbol, include_raw)
        with self._quote_cache_lock:
            cached = self._quote_cache.get(cache_key)
            if cached is None:
                return None
            expires_at, quote = cached
            if expires_at < now:
                self._quote_cache.pop(cache_key, None)
                return None
            return quote

    def _store_cached_quote(self, symbol: str, include_raw: bool, quote: QuoteResponse) -> None:
        ttl_ms = max(0, int(self.settings.quote_cache_ttl_ms))
        if ttl_ms <= 0:
            return
        cache_key = (symbol, include_raw)
        expires_at = time.monotonic() + (ttl_ms / 1000.0)
        with self._quote_cache_lock:
            self._quote_cache[cache_key] = (expires_at, quote)

    def _get_cached_negative_quote(self, symbol: str, include_raw: bool) -> AppError | None:
        ttl_ms = max(0, int(self.settings.quote_negative_cache_ttl_ms))
        if ttl_ms <= 0:
            return None
        now = time.monotonic()
        cache_key = (symbol, include_raw)
        with self._quote_cache_lock:
            cached = self._negative_cache.get(cache_key)
            if cached is None:
                return None
            expires_at, error = cached
            if expires_at < now:
                self._negative_cache.pop(cache_key, None)
                return None
            return error

    def _store_negative_quote(self, symbol: str, include_raw: bool, error: AppError) -> None:
        ttl_ms = max(0, int(self.settings.quote_negative_cache_ttl_ms))
        if ttl_ms <= 0:
            return
        cache_key = (symbol, include_raw)
        expires_at = time.monotonic() + (ttl_ms / 1000.0)
        with self._quote_cache_lock:
            self._negative_cache[cache_key] = (expires_at, error)

    def _acquire_inflight(self, symbol: str, include_raw: bool) -> tuple["_InflightQuote", bool]:
        cache_key = (symbol, include_raw)
        with self._inflight_lock:
            existing = self._inflight_quotes.get(cache_key)
            if existing is not None:
                return existing, False
            inflight = _InflightQuote()
            self._inflight_quotes[cache_key] = inflight
            return inflight, True

    def _release_inflight(
        self,
        symbol: str,
        include_raw: bool,
        inflight: "_InflightQuote",
    ) -> None:
        cache_key = (symbol, include_raw)
        inflight.event.set()
        with self._inflight_lock:
            current = self._inflight_quotes.get(cache_key)
            if current is inflight:
                self._inflight_quotes.pop(cache_key, None)

    def _drop_stale_inflight(
        self,
        symbol: str,
        include_raw: bool,
        inflight: "_InflightQuote",
    ) -> None:
        cache_key = (symbol, include_raw)
        with self._inflight_lock:
            current = self._inflight_quotes.get(cache_key)
            if current is inflight and not inflight.event.is_set():
                self._inflight_quotes.pop(cache_key, None)

    def _inflight_wait_timeout_seconds(self) -> float:
        return max(1.0, float(self.settings.btg_trader_desk_symbol_timeout_seconds) + 0.5)

    @staticmethod
    def _has_meaningful_tick(tick_info: dict[str, Any]) -> bool:
        time_value = MarketDataService._as_int(tick_info.get("time"))
        time_msc = MarketDataService._as_int(tick_info.get("time_msc"))
        if (time_msc or 0) > 0 or (time_value or 0) > 0:
            return True

        bid = MarketDataService._as_float(tick_info.get("bid")) or 0.0
        ask = MarketDataService._as_float(tick_info.get("ask")) or 0.0
        last = MarketDataService._as_float(tick_info.get("last")) or 0.0
        volume_real = MarketDataService._as_float(tick_info.get("volume_real")) or 0.0
        return any(value > 0 for value in (bid, ask, last, volume_real))

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return (symbol or "").strip().upper()

    @staticmethod
    def _tick_timestamp(tick_info: dict[str, Any]) -> datetime | None:
        time_msc = tick_info.get("time_msc")
        if time_msc is not None:
            try:
                return datetime.fromtimestamp(float(time_msc) / 1000.0, tz=UTC)
            except (TypeError, ValueError, OSError):
                pass
        timestamp = tick_info.get("time")
        if timestamp is None:
            return None
        try:
            return datetime.fromtimestamp(float(timestamp), tz=UTC)
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _as_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_bool(value: Any) -> bool | None:
        if value is None:
            return None
        return bool(value)


class _InflightQuote:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.quote: QuoteResponse | None = None
        self.error: AppError | None = None
