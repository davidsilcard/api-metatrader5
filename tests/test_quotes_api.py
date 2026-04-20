from __future__ import annotations

import concurrent.futures
import time

from fastapi.testclient import TestClient

from api_metatrader5.app import create_test_app
from api_metatrader5.core.config import Settings
from api_metatrader5.core.errors import ProviderTimeoutError
from api_metatrader5.security.hmac_auth import build_canonical_message, sha256_hex, sign_message
from api_metatrader5.services.btg_trader_desk_client import BtgTraderDeskClient


class FakeMt5Client:
    def __init__(self) -> None:
        self.tick_calls = 0

    def ensure_connected(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def connection_status(self):
        return {
            "connected": True,
            "state": "connected",
            "reconnect_count": 2,
            "last_connected_at": 1712350000.0,
            "last_error": None,
        }

    def last_error(self):
        return {"code": 0, "message": "ok"}

    def terminal_info(self):
        return {"name": "terminal"}

    def account_info(self):
        return {"login": 123}

    def symbols_get(self, group=None):
        if group and "INVALID1" in group:
            return []
        return [
            {
                "name": "BBDCG189",
                "description": "BBDC option",
                "currency_base": "BRL",
                "currency_profit": "BRL",
                "path": "B3\\Options",
                "digits": 2,
                "visible": True,
                "trade_mode": 4,
            }
        ]

    def symbol_info(self, symbol):
        if symbol in {"BBDCG189", "BBDCG189F"}:
            return {
                "name": symbol,
                "description": "BBDC option",
                "currency_base": "BRL",
                "currency_profit": "BRL",
                "currency_margin": "BRL",
                "digits": 2,
                "point": 0.01,
                "spread": 1,
                "spread_float": True,
                "visible": True,
                "trade_mode": 4,
                "path": "B3\\Options",
                "filling_mode": 2,
            }
        return None

    def symbol_info_tick(self, symbol):
        if symbol in {"BBDCG189", "BBDCG189F"}:
            self.tick_calls += 1
            return {
                "bid": 1.9,
                "ask": 1.91,
                "last": 1.91,
                "volume": 100,
                "volume_real": 100.0,
                "time": 1712350000,
                "time_msc": 1712350000123,
            }
        return None

    def symbol_select(self, symbol, enable):
        return symbol in {"BBDCG189", "BBDCG189F"}

    def order_check(self, request_data):
        return {"retcode": 0, "comment": "ok", "request": request_data}

    def order_send(self, request_data):
        return {"retcode": 10009, "comment": "done", "request": request_data}

    def get_constant(self, name: str):
        constants = {
            "TRADE_ACTION_DEAL": 1,
            "TRADE_ACTION_PENDING": 5,
            "ORDER_TYPE_BUY": 0,
            "ORDER_TYPE_SELL": 1,
            "ORDER_TYPE_BUY_LIMIT": 2,
            "ORDER_TYPE_SELL_LIMIT": 3,
            "ORDER_TYPE_BUY_STOP": 4,
            "ORDER_TYPE_SELL_STOP": 5,
            "ORDER_TYPE_BUY_STOP_LIMIT": 6,
            "ORDER_TYPE_SELL_STOP_LIMIT": 7,
            "ORDER_TIME_GTC": 0,
            "ORDER_TIME_DAY": 1,
            "ORDER_TIME_SPECIFIED": 2,
            "ORDER_FILLING_IOC": 1,
            "ORDER_FILLING_FOK": 0,
            "ORDER_FILLING_RETURN": 2,
        }
        return constants[name]


class TimeoutSymbolClient(FakeMt5Client):
    def __init__(self) -> None:
        super().__init__()
        self.timeout_tick_calls = 0

    def symbol_info(self, symbol):
        if symbol == "WIZCD983":
            return {
                "name": symbol,
                "description": symbol,
                "currency_base": "BRL",
                "currency_profit": "BRL",
                "currency_margin": "BRL",
                "digits": 2,
                "point": 0.01,
                "spread": 0,
                "spread_float": True,
                "visible": True,
                "trade_mode": 4,
                "path": "B3\\Options",
            }
        return super().symbol_info(symbol)

    def symbol_select(self, symbol, enable):
        if symbol == "WIZCD983":
            return True
        return super().symbol_select(symbol, enable)

    def symbol_info_tick(self, symbol):
        if symbol == "WIZCD983":
            self.timeout_tick_calls += 1
            raise ProviderTimeoutError(
                "Provider timeout",
                details={"symbol": symbol},
            )
        return super().symbol_info_tick(symbol)


def auth_headers(*, secret: str, method: str, path: str, query: str = "", body: bytes = b"") -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = f"nonce-{time.time_ns()}"
    canonical = build_canonical_message(
        method=method,
        path=path,
        query=query,
        timestamp=timestamp,
        nonce=nonce,
        body_hash=sha256_hex(body),
    )
    signature = sign_message(secret, canonical)
    return {
        "X-Key-Id": "edge-1",
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }


def test_ready_endpoint_does_not_require_hmac_and_is_minimal() -> None:
    settings = Settings(hmac_shared_keys="edge-1=super-secret")
    app = create_test_app(settings=settings, mt5_client=FakeMt5Client())
    client = TestClient(app)

    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["mt5_connected"] is True
    assert payload["mt5_state"] == "connected"
    assert "terminal" not in payload
    assert "account" not in payload


def test_batch_quotes_returns_partial_success() -> None:
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        hmac_key_scopes="edge-1=quotes:read|symbols:read|orders:preview",
    )
    app = create_test_app(settings=settings, mt5_client=FakeMt5Client())
    client = TestClient(app)

    body = b'{"symbols":["BBDCG189","INVALID1"],"include_raw":false}'
    headers = auth_headers(
        secret="super-secret",
        method="POST",
        path="/internal/v1/quotes/batch",
        body=body,
    )
    headers["Content-Type"] = "application/json"
    response = client.post(
        "/internal/v1/quotes/batch",
        headers=headers,
        content=body,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count_total"] == 2
    assert payload["count_success"] == 1
    assert payload["count_error"] == 1
    assert payload["partial"] is True
    assert payload["items"][0]["ok"] is True
    assert payload["items"][0]["quote"]["raw_tick"] is None
    assert payload["items"][1]["ok"] is False
    assert payload["items"][1]["error"]["code"] == "symbol_not_found"


def test_batch_quotes_isolates_timeout_per_symbol() -> None:
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        hmac_key_scopes="edge-1=quotes:read|symbols:read",
        quote_negative_cache_ttl_ms=1000,
    )
    app = create_test_app(settings=settings, market_data_client=TimeoutSymbolClient())
    client = TestClient(app)

    body = b'{"symbols":["BBDCG189","WIZCD983","BBDCG189"],"include_raw":false}'
    headers = auth_headers(
        secret="super-secret",
        method="POST",
        path="/internal/v1/quotes/batch",
        body=body,
    )
    headers["Content-Type"] = "application/json"
    response = client.post("/internal/v1/quotes/batch", headers=headers, content=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["count_total"] == 3
    assert payload["count_success"] == 2
    assert payload["count_error"] == 1
    assert payload["partial"] is True
    assert payload["items"][0]["ok"] is True
    assert payload["items"][1]["ok"] is False
    assert payload["items"][1]["error"]["code"] == "timeout"
    assert payload["items"][1]["error"]["message"] == "Provider timeout"
    assert payload["items"][1]["error"]["details"]["symbol"] == "WIZCD983"
    assert payload["items"][2]["ok"] is True


def test_search_symbols_uses_query() -> None:
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        hmac_key_scopes="edge-1=quotes:read|symbols:read",
    )
    app = create_test_app(settings=settings, mt5_client=FakeMt5Client())
    client = TestClient(app)

    headers = auth_headers(
        secret="super-secret",
        method="GET",
        path="/internal/v1/symbols/search",
        query="q=BBDC&limit=20",
    )
    response = client.get("/internal/v1/symbols/search?q=BBDC&limit=20", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["symbol"] == "BBDCG189"


def test_metrics_endpoint_exposes_gateway_snapshot() -> None:
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        hmac_key_scopes="edge-1=quotes:read|symbols:read|metrics:read",
    )
    app = create_test_app(settings=settings, mt5_client=FakeMt5Client())
    client = TestClient(app)

    quote_headers = auth_headers(
        secret="super-secret",
        method="GET",
        path="/internal/v1/quotes/BBDCG189",
    )
    quote_response = client.get("/internal/v1/quotes/BBDCG189", headers=quote_headers)
    assert quote_response.status_code == 200

    metrics_headers = auth_headers(
        secret="super-secret",
        method="GET",
        path="/internal/v1/metrics",
    )
    response = client.get("/internal/v1/metrics", headers=metrics_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["global"]["requests"] >= 2
    assert "GET /internal/v1/quotes/BBDCG189" in payload["endpoints"]
    assert payload["mt5"]["connected"] is True
    assert payload["machine"]["cpu_count"] is not None


def test_quote_cache_reuses_recent_quote() -> None:
    fake_client = FakeMt5Client()
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        hmac_key_scopes="edge-1=quotes:read|symbols:read",
        quote_cache_ttl_ms=500,
    )
    app = create_test_app(settings=settings, market_data_client=fake_client)
    client = TestClient(app)

    headers_1 = auth_headers(
        secret="super-secret",
        method="GET",
        path="/internal/v1/quotes/BBDCG189",
        query="include_raw=false",
    )
    response_1 = client.get("/internal/v1/quotes/BBDCG189?include_raw=false", headers=headers_1)
    assert response_1.status_code == 200

    headers_2 = auth_headers(
        secret="super-secret",
        method="GET",
        path="/internal/v1/quotes/BBDCG189",
        query="include_raw=false",
    )
    response_2 = client.get("/internal/v1/quotes/BBDCG189?include_raw=false", headers=headers_2)
    assert response_2.status_code == 200
    assert fake_client.tick_calls == 1


def test_quote_requests_are_coalesced_for_same_symbol() -> None:
    fake_client = FakeMt5Client()
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        quote_cache_ttl_ms=0,
    )
    service = create_test_app(settings=settings, market_data_client=fake_client).state.market_data_service

    original = fake_client.symbol_info_tick

    def slow_tick(symbol):
        time.sleep(0.2)
        return original(symbol)

    fake_client.symbol_info_tick = slow_tick

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(service.get_quote, symbol="BBDCG189", include_raw=False) for _ in range(5)]
        results = [future.result(timeout=5) for future in futures]

    assert all(result.symbol == "BBDCG189" for result in results)
    assert fake_client.tick_calls == 1


def test_batch_reuses_quote_for_duplicate_symbols() -> None:
    fake_client = FakeMt5Client()
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        hmac_key_scopes="edge-1=quotes:read|symbols:read",
        quote_cache_ttl_ms=0,
    )
    app = create_test_app(settings=settings, market_data_client=fake_client)
    client = TestClient(app)

    body = b'{"symbols":["BBDCG189","BBDCG189","INVALID1"],"include_raw":false}'
    headers = auth_headers(
        secret="super-secret",
        method="POST",
        path="/internal/v1/quotes/batch",
        body=body,
    )
    headers["Content-Type"] = "application/json"
    response = client.post("/internal/v1/quotes/batch", headers=headers, content=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["count_total"] == 3
    assert payload["count_success"] == 2
    assert payload["count_error"] == 1
    assert payload["partial"] is True
    assert payload["items"][0]["ok"] is True
    assert payload["items"][1]["ok"] is True
    assert payload["items"][2]["ok"] is False
    assert fake_client.tick_calls == 1


def test_timeout_is_negative_cached_for_repeated_symbol() -> None:
    fake_client = TimeoutSymbolClient()
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        quote_negative_cache_ttl_ms=1000,
    )
    service = create_test_app(settings=settings, market_data_client=fake_client).state.market_data_service

    for _ in range(2):
        try:
            service.get_quote(symbol="WIZCD983", include_raw=False)
        except ProviderTimeoutError:
            pass

    assert fake_client.tick_calls == 0
    assert fake_client.timeout_tick_calls == 1


def test_btg_client_preserves_timeout_error() -> None:
    client = BtgTraderDeskClient(settings=Settings(btg_trader_desk_token="token"))

    def raise_timeout(symbol: str):
        raise ProviderTimeoutError("Provider timeout", details={"symbol": symbol})

    client._query_fields = raise_timeout

    try:
        client.symbol_info_tick("WIZCD983")
    except ProviderTimeoutError as exc:
        assert exc.code == "timeout"
        assert exc.details["symbol"] == "WIZCD983"
    else:
        raise AssertionError("ProviderTimeoutError was not propagated")
