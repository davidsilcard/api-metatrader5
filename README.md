# api-metatrader5

Gateway privado em `FastAPI` para expor cotações do `BTG Trader Desk` via HTTP com autenticação `HMAC`.

O nome do repositório foi mantido, mas o backend de mercado desta fase deixou de usar `MetaTrader 5` e passou a usar o endpoint local do `BTG Trader Desk` em `127.0.0.1:9099`.

## Escopo atual

Implementado:

- `GET /health`
- `GET /ready`
- `GET /internal/v1/quotes/{symbol}`
- `POST /internal/v1/quotes/batch`
- `GET /internal/v1/symbols/search`
- `GET /internal/v1/metrics`

Mantido no contrato, mas ainda não suportado pelo backend BTG desta fase:

- `POST /internal/v1/orders/preview` -> responde `501 not_supported`
- `POST /internal/v1/orders` -> responde `501 not_supported`

## Como funciona

- o `BTG Trader Desk` abre um endpoint TCP local
- o gateway autentica nesse endpoint com handshake textual e token local
- os campos `QUOTE.*` são convertidos para o contrato HTTP já existente
- o consumidor continua falando com esta API via HMAC

Campos BTG validados neste ambiente:

- `QUOTE.LAST_TRADE_PRICE`
- `QUOTE.BID_PRICE`
- `QUOTE.ASK_PRICE`
- `QUOTE.CHANGE_PERCENT`
- `QUOTE.VOLUME`
- `QUOTE.LAST_TRADE_TIME`
- `QUOTE.STATUS`

Ticker de opção validado com sucesso neste ambiente:

- `ITUBE542`

## Requisitos

- Windows com `BTG Trader Desk` instalado e aberto
- Python `3.13+`
- `uv`

## Instalação

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

## Configuração

Variáveis principais:

- `APP_HOST`
- `APP_PORT`
- `MT5_GATEWAY_KEY_ID`
- `MT5_GATEWAY_SHARED_SECRET`
- `MT5_GATEWAY_SCOPES`
- `BTG_TRADER_DESK_HOST`
- `BTG_TRADER_DESK_PORT`
- `BTG_TRADER_DESK_TOKEN`
- `BTG_TRADER_DESK_TIMEOUT_SECONDS`
- `BTG_TRADER_DESK_SYMBOL_TIMEOUT_SECONDS`
- `BTG_TRADER_DESK_SYMBOLS_FILE`
- `BTG_TRADER_DESK_CURRENCY`
- `BTG_TRADER_DESK_DEFAULT_DIGITS`
- `QUOTE_CACHE_TTL_MS`
- `QUOTE_NEGATIVE_CACHE_TTL_MS`
- `MT5_SYMBOL_ALIASES`

Observações:

- `BTG_TRADER_DESK_TOKEN` é obrigatório para o handshake TCP
- `BTG_TRADER_DESK_SYMBOL_TIMEOUT_SECONDS` define o orçamento total por símbolo no provider BTG
- `BTG_TRADER_DESK_SYMBOLS_FILE` é opcional e alimenta `GET /internal/v1/symbols/search`
- sem catálogo local, `symbols/search` só encontra símbolos que já estejam no cache do gateway ou nos aliases configurados
- `QUOTE_CACHE_TTL_MS` controla o cache curto de cotações no gateway. `0` desliga o cache.
- `QUOTE_NEGATIVE_CACHE_TTL_MS` controla o cache curto de timeout por símbolo para evitar repetir consulta travada em rajadas.

Configuração prática recomendada para esta máquina:

- `BTG_TRADER_DESK_HOST=127.0.0.1`
- `BTG_TRADER_DESK_PORT=9099`
- `BTG_TRADER_DESK_SYMBOL_TIMEOUT_SECONDS=3.0`
- `QUOTE_CACHE_TTL_MS=250`
- `QUOTE_NEGATIVE_CACHE_TTL_MS=1000`

## Execução

```powershell
uv run api-metatrader5
```

Ou:

```powershell
uv run uvicorn api_metatrader5.app:create_app --factory --host 127.0.0.1 --port 8000
```

## Runbook de boot

Depois de reiniciar a máquina Windows, siga esta ordem:

1. abrir o `BTG Trader Desk`
2. iniciar o serviço do gateway
3. validar `health`
4. validar `ready`

Comandos:

```powershell
Start-Service mt5-gateway
Get-Service mt5-gateway | Select-Object Name,Status,StartType
Invoke-RestMethod http://100.70.177.96:8000/health | ConvertTo-Json -Depth 6
Invoke-RestMethod http://100.70.177.96:8000/ready | ConvertTo-Json -Depth 6
```

Resultado esperado:

- `Get-Service`: `Status = Running`
- `/health`: `status = "ok"`
- `/ready`: `status = "ready"`
- `/ready`: `provider = "btg_trader_desk"`
- `/ready`: `connected = true`

Se `/health` responder e `/ready` não ficar `ready`, o primeiro ponto a verificar é se o `BTG Trader Desk` está aberto e funcional.

## Teste operacional de quotes

Para validar quotes com HMAC sem depender da aplicacao consumidora, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-quotes-batch.ps1 -Symbols PETR4,VALE3 -Repeat 1
```

O script chama `/ready` antes e depois do teste e envia um unico `quotes/batch`.
Ele aceita `-Symbols PETR4,VALE3`, `-Repeat`, `-DelaySeconds`, `-TimeoutSeconds`
e `-IncludeRaw`.

## Contrato HTTP

Quote unitário:

```text
GET /internal/v1/quotes/PETR4
```

Lote:

```json
POST /internal/v1/quotes/batch
{
  "symbols": ["PETR4", "VALE3"],
  "include_raw": false
}
```

Contrato do batch:

- o gateway retorna `200` quando conseguir processar o lote item a item
- se um símbolo específico travar no provider BTG, o lote volta como sucesso parcial
- cada item problemático retorna `ok=false` com `error.code`, `error.message` e `error.details.symbol`
- erro global só deve acontecer quando o lote inteiro não puder ser processado

Exemplo parcial:

```json
{
  "items": [
    {"requested_symbol": "WIZC3", "ok": true, "quote": {"symbol": "WIZC3"}, "error": null},
    {
      "requested_symbol": "WIZCD983",
      "ok": false,
      "quote": null,
      "error": {
        "code": "timeout",
        "message": "Provider timeout",
        "details": {"symbol": "WIZCD983"}
      }
    }
  ],
  "count_total": 2,
  "count_success": 1,
  "count_error": 1,
  "partial": true
}
```

Busca:

```text
GET /internal/v1/symbols/search?q=PETR&limit=20
```

Readiness:

```json
GET /ready
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

Os campos `mt5_connected` e `mt5_state` foram preservados por compatibilidade com consumidores anteriores, mas agora refletem o backend BTG.

## Estratégia recomendada para o consumidor

Para a outra aplicação usar este gateway da forma mais performática possível:

- preferir `POST /internal/v1/quotes/batch` quando houver mais de um símbolo por ciclo
- evitar rajadas de `GET` unitário para dezenas de símbolos ao mesmo tempo
- se precisar de quote unitário frequente do mesmo ticker, deixar o polling dentro de janelas curtas para aproveitar `QUOTE_CACHE_TTL_MS`
- tratar `error.code=timeout` em nível de item no batch, sem derrubar o ciclo inteiro do consumidor
- manter `include_raw=false` por padrão
- evitar símbolos repetidos em lotes, embora o gateway já deduplique repetições dentro do mesmo batch
- agrupar consultas por ciclo de atualização, em vez de disparar uma request por componente visual
- tratar `symbols/search` como apoio operacional, não como chamada de alta frequência

Padrão recomendado no consumidor:

1. montar a lista única de símbolos do ciclo
2. enviar um único `quotes/batch`
3. distribuir o resultado internamente para telas, regras e cálculos
4. repetir no próximo ciclo respeitando a cadência desejada

Padrão a evitar:

- uma request HTTP por card/tela/widget
- múltiplas requests simultâneas para o mesmo ticker
- polling agressivo com `include_raw=true`

## Autenticação HMAC

Os endpoints em `/internal/*` exigem:

- `X-Key-Id`
- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

String canônica:

```text
{METHOD}\n
{PATH}\n
{QUERY}\n
{TIMESTAMP}\n
{NONCE}\n
{BODY_SHA256_HEX}
```

Assinatura:

```text
hex(HMAC_SHA256(secret, canonical_string))
```

Escopos suportados:

- `quotes:read`
- `symbols:read`
- `orders:preview`
- `orders:send`
- `metrics:read`

## Símbolos e catálogo local

O protocolo BTG validado até agora entrega bem `quotes`, mas não foi mapeado como fonte de catálogo completo de símbolos.

Para `GET /internal/v1/symbols/search`, o gateway aceita um arquivo local em `BTG_TRADER_DESK_SYMBOLS_FILE`:

- `.csv` com colunas `symbol`, `description`, `path`, `digits`, ...
- ou `.txt` com um ticker por linha

Exemplo simples:

```text
PETR4
VALE3
PETRD410
VALEK920
```

## Observabilidade

O endpoint:

- `GET /internal/v1/metrics`

expõe:

- métricas em memória por endpoint
- snapshot do provedor BTG
- snapshot básico da máquina

Campos úteis para acompanhamento:

- `global.requests`
- `global.errors`
- `global.latency_ms.avg`
- `global.latency_ms.p95`
- métricas por endpoint em `endpoints`
- estado do backend em `provider`

## Cache de quotes

O gateway agora suporta cache curto em memória por símbolo e por variante de `include_raw`.

Configuração:

- `QUOTE_CACHE_TTL_MS=250`

Leitura prática:

- use `0` para desligar
- use `100` a `300` ms quando quiser aliviar o backend BTG sem perder muito frescor
- o ganho é maior quando o mesmo ticker é consultado em rajadas curtas

## Coalescência de requests

Além do cache, o gateway também faz coalescência por `(symbol, include_raw)`:

- se várias requests simultâneas do mesmo ticker chegarem ao mesmo tempo, apenas uma consulta real vai ao BTG
- as demais aguardam o mesmo resultado
- isso melhora especialmente cenários com vários consumidores internos pedindo o mesmo ativo

O endpoint `quotes/batch` também deduplica símbolos repetidos dentro do mesmo lote.

O cliente BTG tambem reutiliza por uma janela curta o tick recem-consultado ao montar
`symbol_info`, evitando uma segunda consulta imediata ao Trader Desk no primeiro acesso
ao mesmo simbolo.

## Google Sheets

E possivel testar o gateway a partir de uma planilha Google Sheets usando Apps Script
e `POST /internal/v1/quotes/batch`.

Guia pronto:

- `docs/google-sheets-test.md`

Observacoes importantes:

- o Apps Script roda nos servidores do Google, entao nao acessa `127.0.0.1`, IP de LAN
  ou Tailscale `100.x`
- use uma URL HTTPS publica/proxy para o gateway e mantenha HMAC ativo
- nao exponha a porta local `9099` do `BTG Trader Desk`
- evite formula por celula; use lote unico por atualizacao

## Estudos de carga

Os testes abaixo foram feitos em HTTP real contra o gateway local, com `HMAC`, backend `BTG Trader Desk` e o ticker `ITUBE542`.

### Linha de base

Sem cache e sem coalescência:

- concorrência `1`: `0.76 rps`, média `1308 ms`
- concorrência `5`: `4.13 rps`, média `1176 ms`
- concorrência `10`: `7.26 rps`, média `1281 ms`
- concorrência `20`: `11.94 rps`, média `1495 ms`
- concorrência `30`: `8.46 rps`, média `3145 ms`
- concorrência `40`: `7.75 rps`, média `3425 ms`

Leitura:

- o throughput cresceu até perto de `20` concorrências
- acima disso a latência subiu muito e o throughput começou a piorar

### Com cache curto

Com `QUOTE_CACHE_TTL_MS=250`:

- concorrência `1`: `2.16 rps`, média `463 ms`, `p50 29 ms`
- concorrência `5`: `6.96 rps`, média `684 ms`, `p50 127 ms`
- concorrência `10`: `7.31 rps`, média `931 ms`
- concorrência `20`: `11.22 rps`, média `1563 ms`
- concorrência `30`: `13.07 rps`, média `1927 ms`
- concorrência `40`: `13.85 rps`, média `2345 ms`

Leitura:

- o maior ganho apareceu quando houve repetição forte do mesmo ticker
- em baixa concorrência o cache derrubou bastante a latência mediana

### Com cache + coalescência

Com `QUOTE_CACHE_TTL_MS=250` e coalescência de requests simultâneos:

- concorrência `1`: `2.17 rps`, média `461 ms`, `p50 26 ms`
- concorrência `5`: `7.23 rps`, média `664 ms`, `p50 118 ms`
- concorrência `10`: `7.12 rps`, média `1237 ms`
- concorrência `20`: `11.42 rps`, média `1581 ms`
- concorrência `30`: `14.18 rps`, média `1832 ms`
- concorrência `40`: `16.75 rps`, média `1970 ms`

Leitura:

- o ganho mais forte ficou nas rajadas do mesmo símbolo
- em alta concorrência a fila ficou menor que na linha de base
- a API continuou estável sem erro nas rodadas válidas

### Limite operacional sugerido

Faixa recomendada para produção nesta máquina:

- conservador: `5` a `10` requests simultâneas
- confortável: até `20` requests simultâneas
- tolerável em pico, com repetição forte do mesmo ticker: `30+`

Resumo prático:

- para quote unitário, trate `10` a `20` concorrências como faixa saudável
- para muitos símbolos, prefira `quotes/batch`
- para o mesmo ticker em rajadas, o gateway já está otimizado com cache + coalescência
- acima de `30`, ainda funciona, mas já entra em faixa de latência alta para uso muito sensível a tempo real

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Resultado validado nesta fase:

- `19 passed`

## Limitações atuais

- ordens ainda não foram mapeadas no protocolo do `BTG Trader Desk`
- `symbols/search` depende de catálogo local para busca ampla
- o token e o protocolo TCP do Trader Desk devem ser tratados como detalhe operacional local e podem mudar após atualização do aplicativo
- o maior gargalo atual está no tempo de resposta do `BTG Trader Desk`, não no `FastAPI`

## Próximas etapas

- consolidar um catálogo local confiável de ações e opções
- investigar protocolo de ordens do `BTG Trader Desk`
- decidir se o repositório também deve ser renomeado para refletir o backend BTG
