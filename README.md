# api-metatrader5

Gateway privado em `FastAPI` para ler dados do `MetaTrader 5` em tempo quase real e preparar o fluxo futuro de envio de ordens.

Arquitetura recomendada:

- `mt5-gateway` rodando na maquina Windows com o terminal MT5.
- API publica e WebSocket publicados na VPS.
- VPS e Windows conectados por rede privada (`Tailscale` ou `WireGuard`).
- Trafego VPS -> gateway protegido com `HMAC`.

## Escopo atual

Implementado neste repositório:

- `GET /health`
- `GET /ready`
- `GET /internal/v1/quotes/{symbol}`
- `POST /internal/v1/quotes/batch`
- `GET /internal/v1/symbols/search`
- `POST /internal/v1/orders/preview`
- `POST /internal/v1/orders`

Observações:

- `orders` fica desabilitado por padrão. Para permitir `order_send`, defina `MT5_ENABLE_ORDER_SEND=1`.
- O endpoint de quotes já retorna campos principais e também os blocos `raw_tick` e `raw_symbol` para facilitar a primeira fase de integração.

## Requisitos

- Windows com terminal `MetaTrader 5` instalado.
- Python `3.13+`
- `uv`

## Instalação

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

## Execução

```powershell
uv run api-metatrader5
```

Ou:

```powershell
uv run uvicorn api_metatrader5.app:create_app --factory --host 127.0.0.1 --port 8000
```

## Autenticação HMAC

Os endpoints em `/internal/*` exigem estes headers:

- `X-Key-Id`
- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

String canônica assinada:

```text
{METHOD}\n
{PATH}\n
{QUERY}\n
{TIMESTAMP}\n
{NONCE}\n
{BODY_SHA256_HEX}
```

Onde:

- `METHOD`: verbo HTTP em maiúsculas
- `PATH`: caminho da URL, ex. `/internal/v1/quotes/BBDCG189`
- `QUERY`: query string bruta, sem `?`
- `TIMESTAMP`: Unix epoch em segundos UTC
- `NONCE`: identificador único por requisição
- `BODY_SHA256_HEX`: hash SHA-256 do corpo bruto

Assinatura:

```text
hex(HMAC_SHA256(secret, canonical_string))
```

## Exemplos de uso

Quote unitário:

```text
GET /internal/v1/quotes/BBDCG189
```

Quotes em lote:

```json
POST /internal/v1/quotes/batch
{
  "symbols": ["BBDCG189", "VALEK92"]
}
```

Preview de ordem:

```json
POST /internal/v1/orders/preview
{
  "symbol": "VALEK92",
  "side": "buy",
  "order_type": "limit",
  "volume": 100,
  "price": 1.25,
  "client_order_id": "preview-001"
}
```

## Variáveis de ambiente

- `APP_ENV`
- `APP_LOG_LEVEL`
- `APP_HOST`
- `APP_PORT`
- `HMAC_SHARED_KEYS`
- `HMAC_ALLOWED_CLOCK_SKEW_SECONDS`
- `HMAC_NONCE_TTL_SECONDS`
- `MT5_SYMBOL_ALIASES`
- `MT5_TERMINAL_PATH`
- `MT5_LOGIN`
- `MT5_PASSWORD`
- `MT5_SERVER`
- `MT5_DEFAULT_DEVIATION`
- `MT5_MAGIC_NUMBER`
- `MT5_ORDER_COMMENT_PREFIX`
- `MT5_ENABLE_ORDER_SEND`

## Testes

```powershell
uv run pytest -q
```

## Próximas etapas

- integrar este gateway à edge API da VPS
- adicionar WebSocket no edge
- persistir alias de símbolos e auditoria de ordens no PostgreSQL da VPS
