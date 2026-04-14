# Operacao e Deploy do mt5-gateway

Este guia resume a forma recomendada de operar o `mt5-gateway` em uma maquina Windows dedicada.

## Objetivo operacional

- expor o gateway apenas para a VPS por rede privada
- manter o processo resiliente a reboot e queda de sessão
- evitar dependencia de execucao manual em terminal aberto
- reduzir superficie de ataque e vazamento de segredos

## Topologia recomendada

- `mt5-gateway` roda em uma maquina Windows fisica ou VM dedicada
- a VPS consome a API via `Tailscale` ou `WireGuard`
- a API do gateway deve bindar no IP privado da malha, nao em `0.0.0.0`
- o acesso publico pela internet deve permanecer bloqueado

## Execucao como servico no Windows

Use o gateway como servico do Windows, nao como processo manual em janela aberta.

Opcao pratica:

- `NSSM`
- `WinSW`
- `Task Scheduler` somente se o fluxo for simples e bem testado

Requisitos operacionais:

- iniciar junto com o boot
- reiniciar automaticamente em caso de falha
- registrar logs em arquivo
- permitir `start`, `stop`, `restart` e `status`

## Auto-start no boot

O boot da maquina deve trazer a stack de volta sem intervencao manual.

Checklist minimo:

- o Windows sobe normalmente
- o `MetaTrader 5` abre e faz login
- o `mt5-gateway` sobe como servico
- a API reconecta ao terminal quando necessario
- a VPS consegue consumir a API pela malha privada

## Restart automatico

Configure a politica de restart automatico para o servico da API.

Recomendacoes:

- reiniciar em falha inesperada
- aplicar atraso curto entre tentativas
- limitar loops infinitos de restart agressivo
- registrar a causa da queda antes da retomada

## Bind da API

Em producao, o bind deve ser feito apenas no IP privado da rede privada.

Regras:

- desenvolvimento local pode usar `127.0.0.1`
- producao deve usar o IP privado do `Tailscale` ou `WireGuard`
- nao exponha o processo diretamente em IP publico
- nao publique a porta do gateway para a internet aberta

## Firewall

O firewall do Windows deve aceitar somente o necessario.

Checklist:

- liberar apenas a porta usada pelo gateway
- restringir a origem aos IPs da VPS ou da malha privada
- bloquear outras origens por padrao
- validar que a porta nao responde na internet publica

## Segredos e .env

Regras basicas:

- manter `.env` fora do repositorio
- nunca commitar segredo HMAC real
- usar `.env.example` apenas como referencia de variaveis
- trocar segredos antes de qualquer go-live

Checklist de arquivo:

- `.env` local presente apenas na maquina que executa o gateway
- `.gitignore` cobre o arquivo real de ambiente
- segredo compartilhado forte e unico
- rotacao planejada para manutencao futura

## Go-live em fases

Use liberacao progressiva. Nao habilite tudo no primeiro dia.

### Fase 1

- `GET /health`
- `GET /ready`
- `GET /internal/v1/quotes/{symbol}`
- `POST /internal/v1/quotes/batch`
- `GET /internal/v1/symbols/search`
- `MT5_ENABLE_ORDER_SEND=0`

Objetivo:

- validar conectividade, leitura de mercado e estabilidade basica

### Fase 2

- habilitar `POST /internal/v1/orders/preview`
- manter envio real de ordens desabilitado

Objetivo:

- validar fluxo de preparacao de ordem sem executar trade real

### Fase 3

- habilitar `POST /internal/v1/orders` apenas se a operacao estiver estavel
- ativar somente depois de alguns dias de observacao sem incidentes

Objetivo:

- liberar envio real com controle e visibilidade suficientes

## Checklist de prontidao

Considere pronto para producao quando tudo abaixo estiver atendido:

- sobe sozinho no boot
- reinicia sozinho em caso de falha
- responde somente pela rede privada
- nao expoe segredos no repositorio
- firewall bloqueia acessos fora da malha
- `/ready` nao vaza dados sensiveis
- fluxo de quotes funciona com MT5 real
- o go-live foi feito por fases

## Ordem recomendada de validacao

1. subir o Windows e confirmar auto-start
2. validar login do `MetaTrader 5`
3. validar bind no IP privado
4. validar firewall e ausencia de exposicao publica
5. testar `GET /health`
6. testar `GET /ready`
7. testar quote unitario
8. testar batch de quotes
9. testar simbolos
10. habilitar preview
11. habilitar ordens reais somente ao final
