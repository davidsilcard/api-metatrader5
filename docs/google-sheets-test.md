# Teste via Google Sheets

Este teste valida se o Google Sheets consegue buscar cotacoes pelo gateway HTTP.
Ele nao deve chamar o `BTG Trader Desk` direto. A planilha chama somente o gateway
`/internal/v1/quotes/batch` com HMAC.

## Requisitos

- Gateway rodando e respondendo `/health` e `/ready`.
- URL HTTPS acessivel pela internet publica a partir do Google Apps Script.
- `MT5_GATEWAY_KEY_ID` e segredo HMAC do `.env`.
- Lista de tickers na coluna `A`, a partir da celula `A2`.

Importante: `127.0.0.1`, IP de LAN e IP Tailscale `100.x` nao funcionam a partir
do Google Sheets, porque o script roda nos servidores do Google. Para esse teste,
use um proxy/edge HTTPS protegido por HMAC. Nao exponha a porta local `9099` do
Trader Desk.

## Apps Script

No Google Sheets, abra `Extensoes > Apps Script`, cole o codigo abaixo e salve.
Depois, em `Project Settings > Script properties`, configure:

- `BTG_GATEWAY_BASE_URL`: URL publica do gateway, sem barra final.
- `BTG_GATEWAY_KEY_ID`: normalmente `edge-1`.
- `BTG_GATEWAY_SHARED_SECRET`: segredo HMAC.

```javascript
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('BTG')
    .addItem('Atualizar cotacoes', 'refreshBtgQuotes')
    .addToUi();
}

function refreshBtgQuotes() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return;
  }

  const symbols = sheet
    .getRange(2, 1, lastRow - 1, 1)
    .getValues()
    .flat()
    .map(value => String(value || '').trim().toUpperCase())
    .filter(Boolean);

  const uniqueSymbols = [...new Set(symbols)];
  const resultBySymbol = fetchBtgQuotes_(uniqueSymbols);

  const rows = symbols.map(symbol => {
    const item = resultBySymbol[symbol];
    if (!item || !item.ok) {
      const error = item && item.error ? item.error : {};
      return [symbol, false, '', '', '', error.code || 'not_found', error.message || ''];
    }
    const quote = item.quote || {};
    return [symbol, true, quote.last || '', quote.bid || '', quote.ask || '', '', ''];
  });

  sheet.getRange(1, 2, 1, 7).setValues([
    ['ticker', 'ok', 'last', 'bid', 'ask', 'error_code', 'error_message'],
  ]);
  sheet.getRange(2, 2, rows.length, 7).setValues(rows);
}

function fetchBtgQuotes_(symbols) {
  const props = PropertiesService.getScriptProperties();
  const baseUrl = String(props.getProperty('BTG_GATEWAY_BASE_URL') || '').replace(/\/$/, '');
  const keyId = props.getProperty('BTG_GATEWAY_KEY_ID') || 'edge-1';
  const secret = props.getProperty('BTG_GATEWAY_SHARED_SECRET');
  if (!baseUrl || !secret) {
    throw new Error('Configure BTG_GATEWAY_BASE_URL e BTG_GATEWAY_SHARED_SECRET.');
  }

  const path = '/internal/v1/quotes/batch';
  const body = JSON.stringify({ symbols, include_raw: false });
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const nonce = Utilities.getUuid().replace(/-/g, '');
  const bodyHash = hex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, body));
  const canonical = ['POST', path, '', timestamp, nonce, bodyHash].join('\n');
  const signature = hex_(Utilities.computeHmacSha256Signature(canonical, secret));

  const response = UrlFetchApp.fetch(baseUrl + path, {
    method: 'post',
    contentType: 'application/json',
    payload: body,
    headers: {
      'X-Key-Id': keyId,
      'X-Timestamp': timestamp,
      'X-Nonce': nonce,
      'X-Signature': signature,
    },
    muteHttpExceptions: true,
  });

  const status = response.getResponseCode();
  const text = response.getContentText();
  if (status !== 200) {
    throw new Error('Gateway HTTP ' + status + ': ' + text.slice(0, 200));
  }

  const data = JSON.parse(text);
  const bySymbol = {};
  (data.items || []).forEach(item => {
    bySymbol[item.requested_symbol] = item;
  });
  return bySymbol;
}

function hex_(bytes) {
  return bytes
    .map(byte => (byte < 0 ? byte + 256 : byte).toString(16).padStart(2, '0'))
    .join('');
}
```

## Como testar sem sobrecarregar

1. Comece com 2 ou 3 tickers liquidos, por exemplo `PETR4`, `VALE3`, `ITUB4`.
2. Clique em `BTG > Atualizar cotacoes`.
3. So aumente para opcoes depois que o teste pequeno estiver estavel.
4. Evite formulas por celula para cada ticker. Use sempre um lote unico.

Referencias oficiais:

- Google Apps Script `UrlFetchApp`: https://developers.google.com/apps-script/reference/url-fetch/url-fetch-app
- Funcoes customizadas no Sheets e limite de 30 segundos: https://developers.google.com/apps-script/guides/sheets/functions
