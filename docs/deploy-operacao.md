# Operacao e Deploy do BTG Gateway

Este guia resume a forma recomendada de operar o gateway privado em uma máquina Windows dedicada usando `BTG Trader Desk` como backend de mercado.

O nome do serviço e do repositório ainda pode aparecer como `mt5-gateway` por herança histórica, mas a stack atual de dados usa o `BTG Trader Desk`.

## Objetivo operacional

- expor o gateway apenas para a VPS por rede privada
- manter o processo resiliente a reboot e queda do aplicativo local
- evitar dependência de execução manual em terminal aberto
- reduzir superfície de ataque e vazamento de segredos

## Topologia recomendada

- `btg-gateway` roda em uma máquina Windows física ou VM dedicada
- o `BTG Trader Desk` roda localmente na mesma máquina
- a VPS consome a API via `Tailscale` ou `WireGuard`
- a API do gateway deve bindar no IP privado da malha, não em `0.0.0.0`
- o acesso público pela internet deve permanecer bloqueado

## Execução como serviço no Windows

Use o gateway como serviço do Windows, não como processo manual em janela aberta.

Opções práticas:

- `NSSM`
- `WinSW`
- `Task Scheduler` somente se o fluxo for simples e muito bem testado

### Padrão recomendado: NSSM

Quando o `NSSM` estiver instalado, use os scripts do repositório em PowerShell administrativo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-gateway-service.ps1 -NssmPath 'C:\caminho\para\nssm.exe'
powershell -ExecutionPolicy Bypass -File .\scripts\service-status.ps1
```

Remoção do serviço:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\remove-gateway-service.ps1 -NssmPath 'C:\caminho\para\nssm.exe'
```

O instalador configura:

- startup automático no boot
- restart automático em falha
- logs em `logs\mt5-gateway-stdout.log` e `logs\mt5-gateway-stderr.log`
- bind conforme `APP_HOST` e `APP_PORT` do `.env`

### Estado operacional validado

Configuração confirmada neste ambiente:

- serviço: `mt5-gateway`
- startup: `Auto`
- URL privada validada: `http://100.70.177.96:8000`
- `GET /health`: `200`
- `GET /ready`: `200`
- `GET /internal/v1/metrics`: presente e protegido por HMAC

Lição operacional importante:

- se existirem processos antigos iniciados manualmente na mesma porta, eles podem mascarar o comportamento do serviço
- antes de concluir qualquer validação, confirme o dono da porta `8000`

Comandos úteis em PowerShell administrativo:

```powershell
Start-Service mt5-gateway
Stop-Service mt5-gateway
Restart-Service mt5-gateway
Get-CimInstance Win32_Service -Filter "Name='mt5-gateway'" | Select-Object Name,State,StartMode,PathName
Invoke-RestMethod http://100.70.177.96:8000/health | ConvertTo-Json -Depth 6
Invoke-RestMethod http://100.70.177.96:8000/ready | ConvertTo-Json -Depth 6
& 'C:\Program Files\Tailscale\tailscale.exe' ip -4
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
```

## Rotina manual padrão

Enquanto o serviço definitivo não estiver configurado, use estes scripts do repositório:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-gateway.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop-gateway.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\restart-gateway.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\status-gateway.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check-gateway.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\diagnose-machine.ps1
```

Comportamento esperado:

- `start`: sobe o `uvicorn` com o bind do `.env` e grava PID em `logs\mt5-gateway.pid`
- `stop`: encerra o processo salvo no PID
- `restart`: reaplica `stop` seguido de `start`
- `status`: mostra URL atual, PID, health e IP do `Tailscale` quando disponível
- `check`: faz verificação rápida de `health` e `ready`
- `diagnose-machine`: mostra CPU, memória, top processos e adaptadores de rede

## Pré-requisitos do backend BTG

Antes de subir o gateway, confirme:

- `BTG Trader Desk` instalado
- aplicativo aberto e funcionando na máquina
- endpoint local do Trader Desk disponível em `127.0.0.1:9099`
- `BTG_TRADER_DESK_TOKEN` configurado no `.env`

Sem isso, `/ready` deve cair para `not_ready`.

## Bind da API

Em produção, o bind deve ser feito apenas no IP privado da rede privada.

Regras:

- desenvolvimento local pode usar `127.0.0.1`
- produção deve usar o IP privado do `Tailscale` ou `WireGuard`
- não exponha o processo diretamente em IP público
- não publique a porta do gateway para a internet aberta

## Firewall

O firewall do Windows deve aceitar somente o necessário.

Checklist:

- liberar apenas a porta usada pelo gateway
- restringir a origem aos IPs da VPS ou da malha privada
- bloquear outras origens por padrão
- validar que a porta não responde na internet pública

Regra aplicada neste ambiente:

- nome: `mt5-gateway-tailscale-8000`
- direção: `Inbound`
- ação: `Allow`
- perfil: `Private`
- porta local: `TCP 8000`
- origem esperada: VPS `100.109.190.88`

## Tuning da máquina dedicada

Objetivo:

- manter o Windows o mais dedicado possível ao `BTG Trader Desk` e ao gateway
- reduzir latência e jitter sem abrir mão da segurança

Checklist prático:

- evitar navegador aberto na máquina
- evitar terminais interativos desnecessários
- manter apenas o serviço do gateway ativo na porta `8000`
- preferir `include_raw=false` no consumidor
- preferir `quotes/batch` em vez de várias chamadas unitárias concorrentes
- limitar concorrência inicial do consumidor a `5` ou `10`

Diagnóstico sugerido:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\diagnose-machine.ps1
```

Leitura prática da máquina:

- o maior gargalo atual tende a estar no `BTG Trader Desk`, não no `FastAPI`
- o antivírus ainda pode afetar a responsividade do Windows
- para esta máquina, é importante reduzir processos residentes desnecessários

## Segredos e `.env`

Regras básicas:

- manter `.env` fora do repositório
- nunca commitar segredo HMAC real
- usar `.env.example` apenas como referência
- trocar segredos antes de qualquer go-live

Checklist mínimo:

- `MT5_GATEWAY_SHARED_SECRET` definido
- `BTG_TRADER_DESK_TOKEN` definido
- `APP_HOST` e `APP_PORT` alinhados com o bind desejado
- `QUOTE_CACHE_TTL_MS` ajustado conforme o perfil do consumidor

Configuração prática recomendada nesta fase:

```bash
BTG_TRADER_DESK_HOST=127.0.0.1
BTG_TRADER_DESK_PORT=9099
QUOTE_CACHE_TTL_MS=250
```

## Operação por fases

Use liberação progressiva.

### Fase 1

- `GET /health`
- `GET /ready`
- `GET /internal/v1/quotes/{symbol}`
- `POST /internal/v1/quotes/batch`
- `GET /internal/v1/symbols/search`
- `GET /internal/v1/metrics`

Objetivo:

- validar conectividade, leitura de mercado e estabilidade básica

### Fase 2

- manter consumo real pela VPS
- ajustar catálogo local de símbolos, se necessário
- monitorar `p95`, taxa de erro e disponibilidade do backend BTG

Objetivo:

- estabilizar o consumo em produção privada

### Fase 3

- investigar e mapear protocolo de ordens do `BTG Trader Desk`
- só depois reavaliar `orders/preview` e `orders/send`

Objetivo:

- evoluir o gateway sem quebrar a parte de market data já estabilizada

## Checklist de prontidão

Considere pronto para produção quando tudo abaixo estiver atendido:

- sobe sozinho no boot
- reinicia sozinho em caso de falha
- responde somente pela rede privada
- não expõe segredos no repositório
- firewall bloqueia acessos fora da malha
- `/ready` indica backend conectado
- fluxo de quotes funciona com ações e opções reais
- a VPS consegue consumir o gateway com estabilidade

## Ordem recomendada de validação

1. subir o Windows e confirmar auto-start
2. abrir e validar o `BTG Trader Desk`
3. validar bind no IP privado
4. validar firewall e ausência de exposição pública
5. testar `GET /health`
6. testar `GET /ready`
7. testar quote unitário
8. testar batch de quotes
9. testar `metrics`
10. validar consumo real pela VPS
