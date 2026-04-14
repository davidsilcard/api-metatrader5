from __future__ import annotations

from api_metatrader5.core.config import Settings
from api_metatrader5.services.mt5_client import MetaTrader5Client


class FakeMt5Module:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.shutdown_calls = 0
        self.terminal_calls = 0
        self._initialized = False

    def initialize(self, **_kwargs):
        self.initialize_calls += 1
        self._initialized = True
        return True

    def shutdown(self):
        self.shutdown_calls += 1
        self._initialized = False

    def login(self, **_kwargs):
        return True

    def last_error(self):
        return (0, "ok")

    def terminal_info(self):
        self.terminal_calls += 1
        if self.terminal_calls == 1:
            return None
        return object() if self._initialized else None

    def account_info(self):
        return object()

    def symbols_get(self, group=None):
        return []

    def symbol_info(self, symbol):
        return None

    def symbol_info_tick(self, symbol):
        return None

    def symbol_select(self, symbol, enable):
        return True

    def order_check(self, request_data):
        return None

    def order_send(self, request_data):
        return None


def test_mt5_client_reconnects_when_probe_detects_stale_session() -> None:
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        mt5_reconnect_max_attempts=2,
        mt5_reconnect_backoff_seconds=0,
        mt5_connection_probe_interval_seconds=0,
    )
    client = MetaTrader5Client(settings=settings)
    fake_module = FakeMt5Module()
    client._module = fake_module

    client.ensure_connected()
    assert fake_module.initialize_calls == 1

    client.ensure_connected()
    status = client.connection_status()

    assert fake_module.initialize_calls == 2
    assert fake_module.shutdown_calls >= 1
    assert status["connected"] is True
    assert status["reconnect_count"] == 1
