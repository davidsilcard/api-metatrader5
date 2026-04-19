from __future__ import annotations

import csv
import fnmatch
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..core.config import Settings
from ..core.errors import ProviderConnectionError


@dataclass
class ProviderConnectionState:
    connected: bool = False
    state: str = "disconnected"
    connect_attempts: int = 0
    reconnect_count: int = 0
    last_connected_at: float | None = None
    last_probe_at: float | None = None
    last_error: dict[str, Any] | None = None


class _TraderDeskSession:
    def __init__(self, *, host: str, port: int, token: str, timeout: float) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.file = None

    def __enter__(self) -> "_TraderDeskSession":
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self.file = self.sock.makefile("rwb", buffering=0)
        banner_1 = self._readline()
        banner_2 = self._readline()
        if banner_1 != "server version" or banner_2 != "tok":
            raise ProviderConnectionError(
                "Unexpected BTG Trader Desk handshake.",
                details={"banner_1": banner_1, "banner_2": banner_2},
            )
        self._writeline(self.token)
        auth = self._readline()
        if auth != "ok":
            raise ProviderConnectionError(
                "BTG Trader Desk authentication failed.",
                details={"response": auth},
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.file is not None:
                self.file.close()
        finally:
            if self.sock is not None:
                self.sock.close()

    def query(self, topic: str, symbol: str) -> str | None:
        expected_prefix = f"{topic}|{symbol}|"
        for _ in range(2):
            self._writeline(f"{topic}|{symbol}")
            time.sleep(0.15)
            payloads = self._read_available_payloads()
            for payload in payloads:
                if payload.startswith(expected_prefix):
                    return payload[len(expected_prefix) :]
        return None

    def _readline(self) -> str:
        if self.file is None:
            raise ProviderConnectionError("BTG Trader Desk session is not open.")
        raw = self.file.readline()
        if not raw:
            raise ProviderConnectionError("BTG Trader Desk closed the connection.")
        return raw.decode("utf-8", errors="replace").strip()

    def _writeline(self, line: str) -> None:
        if self.file is None:
            raise ProviderConnectionError("BTG Trader Desk session is not open.")
        self.file.write((line + "\n").encode("utf-8"))

    def _read_available_payloads(self) -> list[str]:
        if self.sock is None:
            raise ProviderConnectionError("BTG Trader Desk session is not open.")
        raw_lines: list[str] = []
        while True:
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                break
            if not data:
                break
            chunk = data.decode("utf-8", errors="replace").strip()
            if chunk:
                raw_lines.extend(part.strip() for part in chunk.splitlines() if part.strip())
            if len(data) < 4096:
                break
        return list(self._split_payloads(raw_lines))

    @staticmethod
    def _split_payloads(lines: Iterable[str]) -> Iterable[str]:
        for line in lines:
            for part in line.split(";"):
                payload = part.strip()
                if payload and "|" in payload:
                    yield payload


class BtgTraderDeskClient:
    QUOTE_FIELD_MAP = {
        "last": "QUOTE.LAST_TRADE_PRICE",
        "bid": "QUOTE.BID_PRICE",
        "ask": "QUOTE.ASK_PRICE",
        "change_percent": "QUOTE.CHANGE_PERCENT",
        "volume": "QUOTE.VOLUME",
        "last_trade_time": "QUOTE.LAST_TRADE_TIME",
        "status": "QUOTE.STATUS",
    }

    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._state = ProviderConnectionState()
        self._symbol_cache: dict[str, dict[str, Any]] = {}
        self._catalog_cache: list[dict[str, Any]] | None = None

    def ensure_connected(self) -> None:
        token = self._token()
        with self._lock:
            self._state.connect_attempts += 1
            self._state.state = "connecting"
        try:
            with self._open_session(token=token):
                pass
        except Exception as exc:
            self._mark_connection_failure(exc=exc)
            raise
        self._mark_connection_success()

    def shutdown(self) -> None:
        with self._lock:
            self._state.connected = False
            self._state.state = "disconnected"

    def connection_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connected": self._state.connected,
                "state": self._state.state,
                "connect_attempts": self._state.connect_attempts,
                "reconnect_count": self._state.reconnect_count,
                "last_connected_at": self._state.last_connected_at,
                "last_probe_at": self._state.last_probe_at,
                "last_error": self._state.last_error,
                "provider": "btg_trader_desk",
                "host": self.settings.btg_trader_desk_host,
                "port": self.settings.btg_trader_desk_port,
            }

    def last_error(self) -> dict[str, Any]:
        with self._lock:
            return self._state.last_error or {"message": "ok"}

    def terminal_info(self) -> dict[str, Any] | None:
        return {
            "provider": "btg_trader_desk",
            "host": self.settings.btg_trader_desk_host,
            "port": self.settings.btg_trader_desk_port,
        }

    def account_info(self) -> dict[str, Any] | None:
        return None

    def symbols_get(self, group: str | None = None) -> list[dict[str, Any]]:
        rows = list(self._catalog_rows())
        for symbol, info in sorted(self._symbol_cache.items()):
            if not any(row.get("name") == symbol for row in rows):
                rows.append(info)
        if not group:
            return rows

        pattern = group.upper()
        return [row for row in rows if fnmatch.fnmatch((row.get("name") or "").upper(), pattern)]

    def symbol_info(self, symbol: str) -> dict[str, Any] | None:
        normalized = self._normalize_symbol(symbol)
        if not normalized:
            return None

        for row in self._catalog_rows():
            if (row.get("name") or "").upper() == normalized:
                return dict(row)

        cached = self._symbol_cache.get(normalized)
        if cached is not None:
            return dict(cached)

        tick = self.symbol_info_tick(normalized)
        if tick is None:
            return None

        info = {
            "name": normalized,
            "description": normalized,
            "currency_base": self.settings.btg_trader_desk_currency,
            "currency_profit": self.settings.btg_trader_desk_currency,
            "currency_margin": self.settings.btg_trader_desk_currency,
            "digits": self.settings.btg_trader_desk_default_digits,
            "point": 10 ** (-self.settings.btg_trader_desk_default_digits),
            "spread": self._spread_from_tick(tick),
            "spread_float": True,
            "visible": True,
            "trade_mode": 4,
            "path": f"BTG\\SYMBOLS\\{normalized}",
        }
        self._symbol_cache[normalized] = info
        return dict(info)

    def symbol_info_tick(self, symbol: str) -> dict[str, Any] | None:
        normalized = self._normalize_symbol(symbol)
        if not normalized:
            return None

        try:
            fields = self._query_fields(normalized)
        except ProviderConnectionError:
            raise
        except Exception as exc:
            self._mark_connection_failure(exc=exc)
            raise ProviderConnectionError(
                "BTG Trader Desk quote query failed.",
                details={"symbol": normalized, "exception_type": exc.__class__.__name__},
            ) from exc

        last = self._to_float(fields["last"])
        bid = self._to_float(fields["bid"])
        ask = self._to_float(fields["ask"])
        volume = self._to_int(fields["volume"])
        if all(value is None for value in (last, bid, ask, volume)):
            return None

        now = time.time()
        return {
            "bid": bid,
            "ask": ask,
            "last": last,
            "volume": volume,
            "volume_real": None if volume is None else float(volume),
            "time": int(now),
            "time_msc": int(now * 1000),
            "change_percent": self._to_float(fields["change_percent"]),
            "last_trade_time": fields["last_trade_time"],
            "status": fields["status"],
            "source": "btg-trader-desk",
        }

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        if not enable:
            return True
        return self.symbol_info(symbol) is not None

    def _open_session(self, *, token: str) -> _TraderDeskSession:
        return _TraderDeskSession(
            host=self.settings.btg_trader_desk_host,
            port=self.settings.btg_trader_desk_port,
            token=token,
            timeout=self.settings.btg_trader_desk_timeout_seconds,
        )

    def _token(self) -> str:
        token = self.settings.btg_trader_desk_token
        if token is None:
            raise ProviderConnectionError(
                "BTG Trader Desk token is not configured.",
                details={"env": "BTG_TRADER_DESK_TOKEN"},
            )
        secret = token.get_secret_value().strip()
        if not secret:
            raise ProviderConnectionError(
                "BTG Trader Desk token is not configured.",
                details={"env": "BTG_TRADER_DESK_TOKEN"},
            )
        return secret

    def _query_fields(self, symbol: str) -> dict[str, str | None]:
        token = self._token()
        with self._open_session(token=token) as session:
            result = {
                key: session.query(topic, symbol)
                for key, topic in self.QUOTE_FIELD_MAP.items()
            }
        self._mark_probe_success()
        return result

    def _catalog_rows(self) -> list[dict[str, Any]]:
        if self._catalog_cache is not None:
            return self._catalog_cache

        rows: list[dict[str, Any]] = []
        path_text = self.settings.btg_trader_desk_symbols_file
        if path_text:
            path = Path(path_text)
            if path.exists():
                if path.suffix.lower() == ".csv":
                    rows = self._load_catalog_csv(path)
                else:
                    rows = self._load_catalog_text(path)
        self._catalog_cache = rows
        return self._catalog_cache

    def _load_catalog_csv(self, path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                symbol = self._normalize_symbol(raw.get("symbol") or raw.get("name"))
                if not symbol:
                    continue
                rows.append(
                    {
                        "name": symbol,
                        "description": (raw.get("description") or symbol).strip(),
                        "path": (raw.get("path") or f"BTG\\SYMBOLS\\{symbol}").strip(),
                        "currency_base": (raw.get("currency_base") or self.settings.btg_trader_desk_currency).strip(),
                        "currency_profit": (raw.get("currency_profit") or self.settings.btg_trader_desk_currency).strip(),
                        "currency_margin": (raw.get("currency_margin") or self.settings.btg_trader_desk_currency).strip(),
                        "digits": self._to_int(raw.get("digits")) or self.settings.btg_trader_desk_default_digits,
                        "visible": self._to_bool(raw.get("visible"), default=True),
                        "trade_mode": self._to_int(raw.get("trade_mode")) or 4,
                        "point": 10 ** (-(self._to_int(raw.get("digits")) or self.settings.btg_trader_desk_default_digits)),
                        "spread": self._to_int(raw.get("spread")) or 0,
                        "spread_float": self._to_bool(raw.get("spread_float"), default=True),
                    }
                )
        return rows

    def _load_catalog_text(self, path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                symbol = self._normalize_symbol(line)
                if not symbol:
                    continue
                rows.append(
                    {
                        "name": symbol,
                        "description": symbol,
                        "path": f"BTG\\SYMBOLS\\{symbol}",
                        "currency_base": self.settings.btg_trader_desk_currency,
                        "currency_profit": self.settings.btg_trader_desk_currency,
                        "currency_margin": self.settings.btg_trader_desk_currency,
                        "digits": self.settings.btg_trader_desk_default_digits,
                        "visible": True,
                        "trade_mode": 4,
                        "point": 10 ** (-self.settings.btg_trader_desk_default_digits),
                        "spread": 0,
                        "spread_float": True,
                    }
                )
        return rows

    def _mark_connection_success(self) -> None:
        with self._lock:
            reconnect = self._state.connected is False and self._state.last_connected_at is not None
            self._state.connected = True
            self._state.state = "connected"
            self._state.last_connected_at = time.time()
            self._state.last_probe_at = self._state.last_connected_at
            self._state.last_error = None
            if reconnect:
                self._state.reconnect_count += 1

    def _mark_probe_success(self) -> None:
        with self._lock:
            self._state.connected = True
            self._state.state = "connected"
            self._state.last_probe_at = time.time()
            self._state.last_error = None

    def _mark_connection_failure(self, *, exc: Exception) -> None:
        details = {"exception_type": exc.__class__.__name__, "message": str(exc)}
        if isinstance(exc, ProviderConnectionError):
            details = exc.details or details
            details.setdefault("exception_type", exc.__class__.__name__)
            details.setdefault("message", exc.message)
        with self._lock:
            self._state.connected = False
            self._state.state = "error"
            self._state.last_probe_at = time.time()
            self._state.last_error = details

    @staticmethod
    def _spread_from_tick(tick: dict[str, Any]) -> int:
        bid = BtgTraderDeskClient._to_float(tick.get("bid"))
        ask = BtgTraderDeskClient._to_float(tick.get("ask"))
        if bid is None or ask is None:
            return 0
        return int(round((ask - bid) * 100))

    @staticmethod
    def _normalize_symbol(value: object) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _to_float(value: object) -> float | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _to_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(float(str(value).strip().replace(",", ".")))
        except ValueError:
            return None

    @staticmethod
    def _to_bool(value: object, *, default: bool) -> bool:
        if value is None:
            return default
        text = str(value).strip().lower()
        if not text:
            return default
        return text in {"1", "true", "t", "yes", "y", "sim"}
