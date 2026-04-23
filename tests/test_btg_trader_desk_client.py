from __future__ import annotations

from pathlib import Path
import threading
import time

from api_metatrader5.core.config import Settings
from api_metatrader5.services.btg_trader_desk_client import BtgTraderDeskClient


class FakeBtgTraderDeskClient(BtgTraderDeskClient):
    def _query_fields(self, symbol: str) -> dict[str, str | None]:
        if symbol == "PETR4":
            return {
                "last": "46.25",
                "bid": "46.22",
                "ask": "46.23",
                "change_percent": "1.15",
                "volume": "12345",
                "last_trade_time": "11:31:00",
                "status": "OPEN",
            }
        return {
            "last": None,
            "bid": None,
            "ask": None,
            "change_percent": None,
            "volume": None,
            "last_trade_time": None,
            "status": None,
        }


def test_btg_symbol_info_tick_parses_quote_fields() -> None:
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        btg_trader_desk_token="token",
    )
    client = FakeBtgTraderDeskClient(settings=settings)

    tick = client.symbol_info_tick("PETR4")

    assert tick is not None
    assert tick["last"] == 46.25
    assert tick["bid"] == 46.22
    assert tick["ask"] == 46.23
    assert tick["volume"] == 12345
    assert tick["status"] == "OPEN"


def test_btg_symbols_get_uses_catalog_file() -> None:
    catalog = Path("tests/.tmp-btg-symbols.csv")
    catalog.write_text(
        "symbol,description,path,digits\n"
        "PETR4,PETROBRAS PN,BTG\\\\ACOES\\\\PETR4,2\n"
        "PETRD410,OPCAO PETR4,BTG\\\\OPCOES\\\\PETRD410,2\n",
        encoding="utf-8",
    )
    try:
        settings = Settings(
            hmac_shared_keys="edge-1=super-secret",
            btg_trader_desk_token="token",
            btg_trader_desk_symbols_file=str(catalog),
        )
        client = FakeBtgTraderDeskClient(settings=settings)

        rows = client.symbols_get(group="*PETR*")

        assert len(rows) == 2
        assert rows[0]["name"] == "PETR4"
        assert rows[1]["name"] == "PETRD410"
    finally:
        if catalog.exists():
            catalog.unlink()


def test_btg_rtd_queries_are_serialized() -> None:
    class SerializedClient(BtgTraderDeskClient):
        def _query_fields_locked(self, *, symbol, token, deadline, result):
            nonlocal active_queries, max_active_queries
            with lock:
                active_queries += 1
                max_active_queries = max(max_active_queries, active_queries)
            time.sleep(0.05)
            with lock:
                active_queries -= 1
            return {
                "last": "1.0",
                "bid": "1.0",
                "ask": "1.0",
                "change_percent": None,
                "volume": "1",
                "last_trade_time": None,
                "status": None,
            }

    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        btg_trader_desk_token="token",
    )
    active_queries = 0
    max_active_queries = 0
    lock = threading.Lock()
    client = SerializedClient(settings=settings)

    threads = [
        threading.Thread(target=client.symbol_info_tick, args=(f"OPT{i}",))
        for i in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert max_active_queries == 1
