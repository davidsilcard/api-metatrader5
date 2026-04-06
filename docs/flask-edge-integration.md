# Integracao Flask -> mt5-gateway

Este documento descreve o fluxo recomendado para o backend Flask da VPS consumir o `mt5-gateway` em modo server-to-server.

## Topologia

- `opcoes.moven.cloud`: app Flask atual
- `api.moven.cloud`: edge API publica na VPS
- `mt5-gateway`: FastAPI privada na maquina Windows com o terminal MT5

Fluxo:

1. o backend Flask recebe a necessidade de buscar mercado ou preparar ordem
2. o backend Flask assina a requisicao HTTP com HMAC
3. a chamada segue pela rede privada entre VPS e Windows
4. o `mt5-gateway` valida assinatura, timestamp e nonce
5. o gateway consulta o MetaTrader 5 local e responde em JSON

## Headers exigidos pelo gateway

- `X-Key-Id`
- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

## String canônica

```text
{METHOD}\n
{PATH}\n
{QUERY}\n
{TIMESTAMP}\n
{NONCE}\n
{BODY_SHA256_HEX}
```

## Exemplo em Python/Flask

```python
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import requests


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_canonical_message(
    *,
    method: str,
    path: str,
    query: str,
    timestamp: str,
    nonce: str,
    body_hash: str,
) -> str:
    return "\n".join(
        [
            method.upper(),
            path,
            query,
            timestamp,
            nonce,
            body_hash,
        ]
    )


def sign_request(
    *,
    secret: str,
    method: str,
    path: str,
    query: str = "",
    body: bytes = b"",
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    canonical_message = build_canonical_message(
        method=method,
        path=path,
        query=query,
        timestamp=timestamp,
        nonce=nonce,
        body_hash=sha256_hex(body),
    )
    signature = hmac.new(
        secret.encode("utf-8"),
        canonical_message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Key-Id": "edge-1",
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }


def fetch_quote(base_url: str, shared_secret: str, symbol: str) -> dict:
    path = f"/internal/v1/quotes/{symbol}"
    headers = sign_request(secret=shared_secret, method="GET", path=path)
    response = requests.get(
        f"{base_url}{path}",
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def preview_order(base_url: str, shared_secret: str) -> dict:
    path = "/internal/v1/orders/preview"
    payload = {
        "symbol": "PETR4",
        "side": "buy",
        "order_type": "limit",
        "volume": 100,
        "price": 48.0,
        "client_order_id": "preview-001",
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = sign_request(
        secret=shared_secret,
        method="POST",
        path=path,
        body=body,
    )
    headers["Content-Type"] = "application/json"
    response = requests.post(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
```

## Variáveis recomendadas na VPS

```bash
MT5_GATEWAY_BASE_URL=http://100.x.y.z:8000
MT5_GATEWAY_KEY_ID=edge-1
MT5_GATEWAY_SHARED_SECRET=troque-por-um-segredo-forte
```

## Regras operacionais

- nunca coloque o segredo HMAC no frontend
- o segredo deve existir apenas no backend Flask/edge
- use rede privada entre VPS e Windows
- gere um `nonce` unico por requisicao
- valide o relogio da VPS e da maquina Windows com NTP

## Comportamento observado na validacao real

- o terminal Clear MT5 respondeu com sucesso a `quotes`
- opcoes inicialmente invisiveis no Market Watch precisaram de `symbol_select`
- para `pending orders` em B3, `time_in_force=day` foi aceito
- comentarios longos na ordem foram rejeitados pelo terminal; o gateway agora usa comentario curto e conservador
