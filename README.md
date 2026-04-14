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
- `GET /ready` devolve apenas estado operacional resumido do gateway e do MT5, sem expor dados detalhados de conta e terminal.
- `POST /internal/v1/quotes/batch` devolve sucesso parcial por símbolo, evitando falha total do lote.

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

Para desenvolvimento local, `127.0.0.1` e aceito.
Em produção, use o IP privado da malha `Tailscale` ou `WireGuard` e bloqueie acesso publico.

## Autenticação HMAC

O gateway aceita duas formas de configurar o segredo:

- simples, para um único consumidor: `MT5_GATEWAY_KEY_ID` + `MT5_GATEWAY_SHARED_SECRET`
- avançada, para rotação ou múltiplas chaves: `HMAC_SHARED_KEYS`

Se `HMAC_SHARED_KEYS` estiver definido, ele tem precedência.

Para autorização por rota, os escopos suportados são:

- `quotes:read`
- `symbols:read`
- `orders:preview`
- `orders:send`

Com uma única chave via `MT5_GATEWAY_SHARED_SECRET`, o default recomendado é liberar apenas `quotes:read`, `symbols:read` e `orders:preview`.

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

Resposta parcial esperada:

```json
{
  "items": [
    {
      "requested_symbol": "BBDCG189",
      "ok": true,
      "quote": {
        "requested_symbol": "BBDCG189",
        "symbol": "BBDCG189",
        "ask": 1.91,
        "bid": 1.9,
        "source": "metatrader5"
      },
      "error": null
    },
    {
      "requested_symbol": "VALEK92",
      "ok": false,
      "quote": null,
      "error": {
        "code": "symbol_not_found",
        "message": "Symbol not found in MetaTrader5.",
        "details": {
          "symbol": "VALEK92"
        }
      }
    }
  ],
  "count_total": 2,
  "count_success": 1,
  "count_error": 1
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

Readiness enxuto:

```json
GET /ready
{
  "status": "ready",
  "mt5_connected": true,
  "mt5_state": "connected",
  "reconnect_count": 0,
  "last_connected_at": 1712350000.0,
  "last_error": null
}
```

## Variáveis de ambiente

- `APP_ENV`
- `APP_LOG_LEVEL`
- `APP_HOST`
- `APP_PORT`
- `APP_LOG_FILE`
- `APP_LOG_MAX_BYTES`
- `APP_LOG_BACKUP_COUNT`
- `MT5_GATEWAY_KEY_ID`
- `MT5_GATEWAY_SHARED_SECRET`
- `MT5_GATEWAY_SCOPES`
- `HMAC_SHARED_KEYS`
- `HMAC_KEY_SCOPES`
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
- `MT5_RECONNECT_MAX_ATTEMPTS`
- `MT5_RECONNECT_BACKOFF_SECONDS`
- `MT5_CONNECTION_PROBE_INTERVAL_SECONDS`

## Testes

```powershell
uv run pytest -q
```

## Operação em máquina dedicada

Se esta máquina ficar dedicada apenas ao `mt5-gateway`, a disputa com outros processos deixa de ser o fator principal. Nesse cenário, o limite real tende a vir da própria stack:

- `FastAPI` + `uvicorn`
- validação `HMAC`
- integração com o terminal `MetaTrader 5`

Leitura prática para capacidade inicial:

- trate `50` requisições concorrentes como uma faixa inicial segura para começar a operar
- entre `50` e `100` concorrências a latência já tende a subir de forma perceptível
- acima disso, o throughput pode parar de crescer e a fila de resposta começa a degradar

Importante:

- testes em memória medem bem o custo da API, autenticação e serialização
- eles não representam rede real, `uvicorn` em processo real nem o comportamento do terminal `MT5`
- o gargalo verdadeiro pode aparecer no `MetaTrader 5` antes da API

Recomendação operacional:

- validar em ambiente real com `uvicorn` rodando localmente
- repetir o benchmark com o terminal `MT5` aberto, logado e consultando símbolos reais
- definir limite operacional por latência `p95`, não apenas por throughput bruto
- se o consumidor gerar rajadas, preferir agregação de cotações e controle de concorrência

Alvo inicial sugerido:

- `p95 < 200 ms` para consulta simples de quote
- taxa de erro `0%`
- uso de CPU estável, sem saturação prolongada

Resumo objetivo:

- máquina dedicada ajuda bastante
- mesmo assim, o limite seguro deve ser validado com HTTP real e `MT5` real
- até essa medição final, considere `50` concorrências como ponto inicial conservador

## Deploy operacional

O guia de operação e deploy ficou separado para facilitar uso no dia a dia:

- [docs/deploy-operacao.md](docs/deploy-operacao.md)

Esse material cobre:

- execução como serviço no Windows
- auto-start no boot
- restart automático
- bind apenas no IP privado da malha
- firewall
- `.env` fora do repositório
- checklist de go-live em fases

## Integracao com a VPS

Referencia pratica para o backend Flask assinar chamadas HMAC:

- `docs/flask-edge-integration.md`

## Próximas etapas

- integrar este gateway à edge API da VPS
- adicionar WebSocket no edge
- persistir alias de símbolos e auditoria de ordens no PostgreSQL da VPS
