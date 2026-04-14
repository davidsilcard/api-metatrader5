from __future__ import annotations

import time

from fastapi.testclient import TestClient

from api_metatrader5.app import create_test_app
from api_metatrader5.core.config import Settings
from api_metatrader5.security.hmac_auth import build_canonical_message, sha256_hex, sign_message


class FakeMt5Client:
    def ensure_connected(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def connection_status(self):
        return {
            "connected": True,
            "state": "connected",
            "reconnect_count": 0,
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
        return [{"name": "BBDCG189", "description": "BBDC option"}]

    def symbol_info(self, symbol):
        if symbol == "BBDCG189":
            return {
                "name": "BBDCG189",
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
        if symbol == "BBDCG189":
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
        return True

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


def build_headers(
    secret: str,
    *,
    method: str,
    path: str,
    key_id: str = "edge-1",
    query: str = "",
    body: bytes = b"",
) -> dict[str, str]:
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
        "X-Key-Id": key_id,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }


def test_quotes_endpoint_requires_valid_hmac() -> None:
    settings = Settings(hmac_shared_keys="edge-1=super-secret")
    app = create_test_app(settings=settings, mt5_client=FakeMt5Client())
    client = TestClient(app)

    response = client.get("/internal/v1/quotes/BBDCG189")
    assert response.status_code == 401


def test_quotes_endpoint_accepts_valid_hmac_with_scope() -> None:
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        hmac_key_scopes="edge-1=quotes:read|symbols:read",
    )
    app = create_test_app(settings=settings, mt5_client=FakeMt5Client())
    client = TestClient(app)

    headers = build_headers("super-secret", method="GET", path="/internal/v1/quotes/BBDCG189")
    response = client.get("/internal/v1/quotes/BBDCG189", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BBDCG189"
    assert payload["ask"] == 1.91


def test_orders_endpoint_rejects_key_without_send_scope() -> None:
    settings = Settings(
        hmac_shared_keys="edge-1=super-secret",
        hmac_key_scopes="edge-1=quotes:read|orders:preview",
        mt5_enable_order_send=True,
    )
    app = create_test_app(settings=settings, mt5_client=FakeMt5Client())
    client = TestClient(app)

    body = (
        b'{"symbol":"BBDCG189","side":"buy","order_type":"market","volume":1,'
        b'"client_order_id":"oid-1"}'
    )
    headers = build_headers(
        "super-secret",
        method="POST",
        path="/internal/v1/orders",
        body=body,
    )
    headers["Content-Type"] = "application/json"
    response = client.post("/internal/v1/orders", headers=headers, content=body)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_quotes_endpoint_accepts_mt5_gateway_secret_fallback() -> None:
    settings = Settings(
        hmac_shared_keys="",
        mt5_gateway_key_id="consumer-app",
        mt5_gateway_shared_secret="super-secret",
        mt5_gateway_scopes="quotes:read,symbols:read",
    )
    app = create_test_app(settings=settings, mt5_client=FakeMt5Client())
    client = TestClient(app)

    headers = build_headers(
        "super-secret",
        method="GET",
        path="/internal/v1/quotes/BBDCG189",
        key_id="consumer-app",
    )
    response = client.get("/internal/v1/quotes/BBDCG189", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BBDCG189"
