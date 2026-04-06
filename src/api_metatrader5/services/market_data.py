from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..core.config import Settings
from ..core.errors import MarketDataUnavailableError, SymbolNotFoundError
from ..schemas.market import QuoteResponse, SymbolSearchItem
from .mt5_client import Mt5ClientProtocol


class MarketDataService:
    def __init__(self, *, settings: Settings, client: Mt5ClientProtocol) -> None:
        self.settings = settings
        self.client = client

    def readiness(self) -> dict[str, Any]:
        try:
            terminal = self.client.terminal_info()
            account = self.client.account_info()
        except Exception as exc:
            return {
                "status": "not_ready",
                "mt5_connected": False,
                "details": {"exception_type": exc.__class__.__name__, "message": str(exc)},
            }
        return {
            "status": "ready",
            "mt5_connected": True,
            "terminal": terminal,
            "account": account,
        }

    def get_quote(self, *, symbol: str, include_raw: bool = True) -> QuoteResponse:
        requested_symbol = self._normalize_symbol(symbol)
        resolved_symbol, symbol_info = self._resolve_symbol_info(requested_symbol)
        tick_info = self._get_tick_with_select_retry(resolved_symbol)
        if not tick_info:
            raise MarketDataUnavailableError(
                "No tick data available for symbol.",
                details={"symbol": resolved_symbol},
            )

        time_utc = self._tick_timestamp(tick_info)
        return QuoteResponse(
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
        )

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
            "Symbol not found in MetaTrader5.",
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
