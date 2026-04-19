# Integracao Flask -> BTG Gateway

Este documento descreve o fluxo recomendado para o backend Flask da VPS consumir este gateway privado em modo server-to-server.

O nome histórico do projeto ficou como `mt5-gateway`, mas o backend de mercado desta fase é o `BTG Trader Desk` local.

## Topologia

- `opcoes.moven.cloud`: app Flask atual
- `api.moven.cloud`: edge API publica na VPS
- `btg-gateway`: FastAPI privada na maquina Windows
- `BTG Trader Desk`: aplicativo local na mesma maquina Windows, expondo o endpoint TCP local

Fluxo:

1. o backend Flask identifica quais símbolos precisa atualizar
2. o backend Flask monta uma lista única de símbolos do ciclo
3. o backend Flask assina a requisição HTTP com HMAC
4. a chamada segue pela rede privada entre VPS e Windows
5. o gateway valida assinatura, timestamp e nonce
6. o gateway consulta o `BTG Trader Desk` local
7. o gateway responde em JSON

## Estratégia recomendada de consumo

Para melhor performance, o consumidor Flask deve operar assim:

1. consolidar a lista única de símbolos do ciclo
2. usar `POST /internal/v1/quotes/batch`
3. distribuir internamente o resultado para telas, regras e cálculos
4. repetir no próximo ciclo

Evite:

- uma request por widget
- várias requests simultâneas para o mesmo ticker
- polling agressivo com `include_raw=true`
- usar `symbols/search` como chamada de alta frequência

Regra prática:

- `1` símbolo isolado: `GET /internal/v1/quotes/{symbol}`
- `2+` símbolos no mesmo ciclo: `POST /internal/v1/quotes/batch`

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
    key_id: str,
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
        "X-Key-Id": key_id,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }


def fetch_quote(base_url: str, key_id: str, shared_secret: str, symbol: str) -> dict:
    path = f"/internal/v1/quotes/{symbol}"
    query = "include_raw=false"
    headers = sign_request(
        key_id=key_id,
        secret=shared_secret,
        method="GET",
        path=path,
        query=query,
    )
    response = requests.get(
        f"{base_url}{path}?{query}",
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def fetch_quotes_batch(
    base_url: str,
    key_id: str,
    shared_secret: str,
    symbols: list[str],
) -> dict:
    path = "/internal/v1/quotes/batch"
    payload = {
        "symbols": symbols,
        "include_raw": False,
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = sign_request(
        key_id=key_id,
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
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def fetch_metrics(base_url: str, key_id: str, shared_secret: str) -> dict:
    path = "/internal/v1/metrics"
    headers = sign_request(
        key_id=key_id,
        secret=shared_secret,
        method="GET",
        path=path,
    )
    response = requests.get(
        f"{base_url}{path}",
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
MT5_GATEWAY_SCOPES=quotes:read,symbols:read,metrics:read
```

No gateway Windows, a mesma chave pode ser configurada de forma simples com:

```bash
MT5_GATEWAY_KEY_ID=edge-1
MT5_GATEWAY_SHARED_SECRET=troque-por-um-segredo-forte
MT5_GATEWAY_SCOPES=quotes:read,symbols:read,metrics:read
```

Se você precisar manter mais de uma chave ativa ao mesmo tempo, use:

```bash
HMAC_SHARED_KEYS=edge-1=segredo-1,edge-2=segredo-2
HMAC_KEY_SCOPES=edge-1=quotes:read|symbols:read|metrics:read
```

## Comportamento atual do contrato

Implementado e recomendado para produção desta fase:

- `GET /health`
- `GET /ready`
- `GET /internal/v1/quotes/{symbol}`
- `POST /internal/v1/quotes/batch`
- `GET /internal/v1/symbols/search`
- `GET /internal/v1/metrics`

Mantido no contrato, mas ainda não suportado pelo backend BTG:

- `POST /internal/v1/orders/preview` -> `501 not_supported`
- `POST /internal/v1/orders` -> `501 not_supported`

## Readiness

Exemplo:

```json
{
  "status": "ready",
  "provider": "btg_trader_desk",
  "connected": true,
  "state": "connected",
  "mt5_connected": true,
  "mt5_state": "connected",
  "reconnect_count": 0,
  "last_connected_at": 1712350000.0,
  "last_error": null
}
```

Notas:

- `provider`, `connected` e `state` são os campos novos mais úteis
- `mt5_connected` e `mt5_state` foram preservados por compatibilidade retroativa

## Batch parcial

O retorno de `quotes/batch` continua item a item:

```json
{
  "items": [
    {
      "requested_symbol": "PETR4",
      "ok": true,
      "quote": {
        "requested_symbol": "PETR4",
        "symbol": "PETR4",
        "last": 46.27,
        "bid": 46.22,
        "ask": 46.40,
        "source": "btg-trader-desk"
      },
      "error": null
    },
    {
      "requested_symbol": "SIMBOLO_INVALIDO",
      "ok": false,
      "quote": null,
      "error": {
        "code": "symbol_not_found",
        "message": "Symbol not found in configured market data provider.",
        "details": {
          "symbol": "SIMBOLO_INVALIDO"
        }
      }
    }
  ],
  "count_total": 2,
  "count_success": 1,
  "count_error": 1
}
```

## Performance observada

Os testes reais foram feitos com o ticker `ITUBE542`.

Leitura prática para o consumidor:

- faixa conservadora: `5` a `10` requests simultâneas
- faixa confortável: até `20`
- acima de `20`, só vale a pena quando há muita repetição do mesmo ticker e o gateway consegue aproveitar cache + coalescência

Configuração recomendada do gateway:

```bash
BTG_TRADER_DESK_HOST=127.0.0.1
BTG_TRADER_DESK_PORT=9099
QUOTE_CACHE_TTL_MS=250
```

Otimizações já implementadas no gateway:

- cache curto de quotes por símbolo
- coalescência de requests simultâneos do mesmo ticker
- deduplicação de símbolos repetidos dentro do mesmo batch

Implicação prática:

- se o Flask fizer polling do mesmo ticker em janelas curtas, o gateway segura melhor
- se o Flask mandar lotes únicos por ciclo, o resultado é melhor do que várias requests separadas

## Regras operacionais

- nunca coloque o segredo HMAC no frontend
- o segredo deve existir apenas no backend Flask/edge
- use rede privada entre VPS e Windows
- gere um `nonce` único por requisição
- valide o relógio da VPS e da máquina Windows com NTP
- mantenha o `BTG Trader Desk` aberto e funcional na máquina Windows
- opere o gateway como serviço do Windows quando a fase de integração estabilizar
- bind do gateway apenas no IP privado da malha `Tailscale` ou `WireGuard`
- bloqueie acesso fora da rede privada no firewall
- mantenha o arquivo `.env` fora do repositório

## Observabilidade recomendada

Consuma `GET /internal/v1/metrics` para acompanhar:

- `global.requests`
- `global.errors`
- `global.latency_ms.avg`
- `global.latency_ms.p95`
- `provider.connected`
- `provider.last_error`

Isso ajuda a distinguir:

- problema na aplicação Flask
- problema no gateway
- problema no `BTG Trader Desk`
- degradação por excesso de concorrência

## Símbolos e catálogo local

`symbols/search` depende de um catálogo local configurado em:

```bash
BTG_TRADER_DESK_SYMBOLS_FILE=C:\caminho\symbols.csv
```

Formatos aceitos:

- `.csv` com colunas `symbol`, `description`, `path`, `digits`, ...
- `.txt` com um ticker por linha

Se o catálogo não estiver configurado:

- o gateway ainda consegue cotar um símbolo conhecido diretamente
- mas a busca ampla de símbolos fica limitada

## Referência operacional complementar

Para o checklist de deploy e operação:

- `docs/deploy-operacao.md`
