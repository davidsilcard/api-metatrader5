from __future__ import annotations

import importlib
import threading
from typing import Any, Protocol

from ..core.config import Settings
from ..core.errors import Mt5ConnectionError


class Mt5ClientProtocol(Protocol):
    def ensure_connected(self) -> None: ...

    def shutdown(self) -> None: ...

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


class MetaTrader5Client:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._module = None
        self._initialized = False

    def _load_module(self):
        if self._module is None:
            self._module = importlib.import_module("MetaTrader5")
        return self._module

    def ensure_connected(self) -> None:
        module = self._load_module()
        with self._lock:
            if self._initialized:
                return

            initialize_kwargs: dict[str, Any] = {}
            if self.settings.mt5_terminal_path:
                initialize_kwargs["path"] = self.settings.mt5_terminal_path

            initialized = module.initialize(**initialize_kwargs)
            if not initialized:
                error = self.last_error()
                raise Mt5ConnectionError(
                    "Unable to initialize MetaTrader5 terminal.",
                    details=error,
                )

            if (
                self.settings.mt5_login is not None
                and self.settings.mt5_password is not None
                and self.settings.mt5_server
            ):
                logged_in = module.login(
                    login=self.settings.mt5_login,
                    password=self.settings.mt5_password.get_secret_value(),
                    server=self.settings.mt5_server,
                )
                if not logged_in:
                    error = self.last_error()
                    raise Mt5ConnectionError(
                        "MetaTrader5 login failed.",
                        details=error,
                    )

            self._initialized = True

    def shutdown(self) -> None:
        if self._module is None:
            return
        with self._lock:
            if self._initialized:
                self._module.shutdown()
                self._initialized = False

    def last_error(self) -> dict[str, Any]:
        module = self._load_module()
        code, message = module.last_error()
        return {"code": code, "message": message}

    def terminal_info(self) -> dict[str, Any] | None:
        self.ensure_connected()
        return self._as_dict(self._load_module().terminal_info())

    def account_info(self) -> dict[str, Any] | None:
        self.ensure_connected()
        return self._as_dict(self._load_module().account_info())

    def symbols_get(self, group: str | None = None) -> list[dict[str, Any]]:
        self.ensure_connected()
        module = self._load_module()
        if group:
            symbols = module.symbols_get(group=group)
        else:
            symbols = module.symbols_get()
        return [self._as_dict(item) for item in (symbols or [])]

    def symbol_info(self, symbol: str) -> dict[str, Any] | None:
        self.ensure_connected()
        return self._as_dict(self._load_module().symbol_info(symbol))

    def symbol_info_tick(self, symbol: str) -> dict[str, Any] | None:
        self.ensure_connected()
        return self._as_dict(self._load_module().symbol_info_tick(symbol))

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        self.ensure_connected()
        return bool(self._load_module().symbol_select(symbol, enable))

    def order_check(self, request_data: dict[str, Any]) -> dict[str, Any] | None:
        self.ensure_connected()
        return self._as_dict(self._load_module().order_check(request_data))

    def order_send(self, request_data: dict[str, Any]) -> dict[str, Any] | None:
        self.ensure_connected()
        return self._as_dict(self._load_module().order_send(request_data))

    def get_constant(self, name: str) -> int:
        module = self._load_module()
        value = getattr(module, name, None)
        if value is None:
            raise Mt5ConnectionError(f"MetaTrader5 constant not available: {name}")
        return int(value)

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
