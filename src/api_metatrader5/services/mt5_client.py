from __future__ import annotations

import importlib
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from ..core.config import Settings
from ..core.errors import Mt5ConnectionError


class Mt5ClientProtocol(Protocol):
    def ensure_connected(self) -> None: ...

    def shutdown(self) -> None: ...

    def connection_status(self) -> dict[str, Any]: ...

    def last_error(self) -> dict[str, Any]: ...

    def terminal_info(self) -> dict[str, Any] | None: ...

    def account_info(self) -> dict[str, Any] | None: ...

    def symbols_get(self, group: str | None = None) -> list[dict[str, Any]]: ...

    def symbol_info(self, symbol: str) -> dict[str, Any] | None: ...

    def symbol_info_tick(self, symbol: str) -> dict[str, Any] | None: ...

    def symbol_select(self, symbol: str, enable: bool) -> bool: ...

    def order_check(self, request_data: dict[str, Any]) -> dict[str, Any] | None: ...

    def order_send(self, request_data: dict[str, Any]) -> dict[str, Any] | None: ...

    def get_constant(self, name: str) -> int: ...


@dataclass
class Mt5ConnectionState:
    connected: bool = False
    state: str = "disconnected"
    connect_attempts: int = 0
    reconnect_count: int = 0
    last_connected_at: float | None = None
    last_probe_at: float | None = None
    last_error: dict[str, Any] | None = None


class MetaTrader5Client:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._module = None
        self._initialized = False
        self._state = Mt5ConnectionState()

    def _load_module(self):
        if self._module is None:
            self._module = importlib.import_module("MetaTrader5")
        return self._module

    def ensure_connected(self) -> None:
        module = self._load_module()
        with self._lock:
            if self._initialized and self._connection_is_fresh_locked():
                return
            self._connect_locked(module, reconnect=self._initialized)

    def shutdown(self) -> None:
        if self._module is None:
            return
        with self._lock:
            if self._initialized:
                self._module.shutdown()
                self._initialized = False
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
            }

    def last_error(self) -> dict[str, Any]:
        module = self._load_module()
        code, message = module.last_error()
        return {"code": code, "message": message}

    def terminal_info(self) -> dict[str, Any] | None:
        return self._call_with_connection(lambda module: self._as_dict(module.terminal_info()))

    def account_info(self) -> dict[str, Any] | None:
        return self._call_with_connection(lambda module: self._as_dict(module.account_info()))

    def symbols_get(self, group: str | None = None) -> list[dict[str, Any]]:
        def _fetch(module):
            if group:
                return module.symbols_get(group=group)
            return module.symbols_get()

        symbols = self._call_with_connection(_fetch)
        return [self._as_dict(item) for item in (symbols or [])]

    def symbol_info(self, symbol: str) -> dict[str, Any] | None:
        return self._call_with_connection(
            lambda module: self._as_dict(module.symbol_info(symbol)),
        )

    def symbol_info_tick(self, symbol: str) -> dict[str, Any] | None:
        return self._call_with_connection(
            lambda module: self._as_dict(module.symbol_info_tick(symbol)),
        )

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        result = self._call_with_connection(lambda module: module.symbol_select(symbol, enable))
        return bool(result)

    def order_check(self, request_data: dict[str, Any]) -> dict[str, Any] | None:
        return self._call_with_connection(
            lambda module: self._as_dict(module.order_check(request_data)),
        )

    def order_send(self, request_data: dict[str, Any]) -> dict[str, Any] | None:
        return self._call_with_connection(
            lambda module: self._as_dict(module.order_send(request_data)),
        )

    def get_constant(self, name: str) -> int:
        module = self._load_module()
        value = getattr(module, name, None)
        if value is None:
            raise Mt5ConnectionError(f"MetaTrader5 constant not available: {name}")
        return int(value)

    def _call_with_connection(self, operation):
        attempts = max(1, int(self.settings.mt5_reconnect_max_attempts))
        last_exception: Exception | None = None
        for attempt in range(1, attempts + 1):
            self.ensure_connected()
            module = self._load_module()
            try:
                result = operation(module)
            except Exception as exc:
                last_exception = exc
                self._mark_connection_failure(exc=exc)
                self._reset_connection()
                self._sleep_before_retry(attempt, attempts)
                continue
            self._mark_probe_success()
            return result

        if last_exception is not None:
            raise Mt5ConnectionError(
                "MetaTrader5 operation failed after reconnection attempts.",
                details={"exception_type": last_exception.__class__.__name__},
            ) from last_exception
        raise Mt5ConnectionError("MetaTrader5 operation failed after reconnection attempts.")

    def _connect_locked(self, module, *, reconnect: bool) -> None:
        attempts = max(1, int(self.settings.mt5_reconnect_max_attempts))
        last_error: dict[str, Any] | None = None
        self._state.state = "reconnecting" if reconnect else "connecting"

        for attempt in range(1, attempts + 1):
            self._state.connect_attempts += 1
            if reconnect or self._initialized:
                try:
                    module.shutdown()
                except Exception:
                    pass
                self._initialized = False

            initialize_kwargs: dict[str, Any] = {}
            if self.settings.mt5_terminal_path:
                initialize_kwargs["path"] = self.settings.mt5_terminal_path

            initialized = module.initialize(**initialize_kwargs)
            if initialized and self._login_if_needed_locked(module):
                self._initialized = True
                self._state.connected = True
                self._state.state = "connected"
                self._state.last_connected_at = time.time()
                self._state.last_probe_at = self._state.last_connected_at
                self._state.last_error = None
                if reconnect:
                    self._state.reconnect_count += 1
                return

            last_error = self.last_error()
            self._state.last_error = last_error
            self._state.connected = False
            self._state.state = "reconnecting" if attempt < attempts else "error"
            self._sleep_before_retry(attempt, attempts)

        raise Mt5ConnectionError(
            "Unable to initialize MetaTrader5 terminal.",
            details=last_error or {"message": "unknown error"},
        )

    def _login_if_needed_locked(self, module) -> bool:
        if (
            self.settings.mt5_login is None
            or self.settings.mt5_password is None
            or not self.settings.mt5_server
        ):
            return True

        logged_in = module.login(
            login=self.settings.mt5_login,
            password=self.settings.mt5_password.get_secret_value(),
            server=self.settings.mt5_server,
        )
        return bool(logged_in)

    def _connection_is_fresh_locked(self) -> bool:
        if not self._initialized:
            return False
        now = time.time()
        if self._state.last_probe_at is not None:
            age = now - self._state.last_probe_at
            if age < max(0, int(self.settings.mt5_connection_probe_interval_seconds)):
                return self._state.connected

        terminal = self._as_dict(self._load_module().terminal_info())
        self._state.last_probe_at = now
        if terminal is None:
            self._state.connected = False
            self._state.state = "stale"
            self._state.last_error = self.last_error()
            return False

        self._state.connected = True
        self._state.state = "connected"
        self._state.last_error = None
        return True

    def _mark_connection_failure(self, *, exc: Exception) -> None:
        with self._lock:
            self._state.connected = False
            self._state.state = "error"
            self._state.last_probe_at = time.time()
            self._state.last_error = {
                "exception_type": exc.__class__.__name__,
                "message": str(exc),
            }

    def _mark_probe_success(self) -> None:
        with self._lock:
            self._state.connected = True
            self._state.state = "connected"
            self._state.last_probe_at = time.time()

    def _reset_connection(self) -> None:
        with self._lock:
            if self._module is not None and self._initialized:
                try:
                    self._module.shutdown()
                except Exception:
                    pass
            self._initialized = False
            self._state.connected = False
            self._state.state = "reconnecting"

    def _sleep_before_retry(self, attempt: int, attempts: int) -> None:
        if attempt >= attempts:
            return
        delay = max(0.0, float(self.settings.mt5_reconnect_backoff_seconds))
        if delay > 0:
            time.sleep(delay)

    def _as_dict(self, payload: Any) -> dict[str, Any] | None:
        if payload is None:
            return None
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "_asdict"):
            return payload._asdict()
        if hasattr(payload, "__dict__"):
            return dict(vars(payload))
        return {"value": payload}
