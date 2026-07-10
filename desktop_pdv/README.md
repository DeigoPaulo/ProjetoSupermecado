# PDV Desktop

Shell Windows do PDV operacional. Ele abre a mesma interface Django usada em
`/pdv/` dentro de uma WebView e reserva uma ponte local para impressora, gaveta,
balanca e TEF.

A ponte `window.SupermercadoDesktop.printSale(payload)` imprime venda,
`window.SupermercadoDesktop.printLabels(payload)` gera etiquetas ZPL ou EPL/PPLB
e envia o lote diretamente ao spooler Windows em modo RAW. PPLA permanece
bloqueado ate a homologacao do adaptador para o modelo fisico da impressora.

A balanca usa o contrato `pdv_scale_v1` recebido no bootstrap do terminal. A ponte
local expoe `scaleConfig()` e `readScale()` com fallback manual; enquanto o driver
fisico serial/TCP ainda nao estiver conectado, e possivel homologar a tela com
`SUPERMERCADO_PDV_PESO_SIMULADO=1,250`. Falhas e retornos manuais da balanca
sao gravados em `devices.log.jsonl` na pasta local do terminal e podem ser
consultados pela ponte `window.SupermercadoDesktop.deviceLogs()`.

## Desenvolvimento

1. Instale as dependencias com `pip install -r requirements.txt`.
2. Execute `python app.py`.
3. Na primeira abertura, informe servidor, identificador e chave do terminal.

O app valida a licenca em `/pdv/api/terminal/bootstrap/` antes de abrir o PDV.
A ativacao e validada antes de ser salva. No Windows, a configuracao fica em
`%LOCALAPPDATA%\SupermercadoPDV\config.json`; para reconfigurar, execute o app
com `--configurar`. A chave fica apenas na maquina do caixa e nao e versionada.

## Build Windows

Execute `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`. O
executavel sera criado em `dist\SupermercadoPDV.exe`. Assinatura digital e
geracao do instalador MSI ainda fazem parte da etapa de distribuicao.

Depois do build e da assinatura, execute
`powershell -ExecutionPolicy Bypass -File .\publish_windows.ps1 -Version 0.1.0`.
O script confere o SHA-256 e publica o arquivo de forma atomica em `artifacts`,
de onde a central do ERP passa a disponibiliza-lo ao admin master.

O empacotamento Windows sera feito a partir deste projeto separado. O ERP web
continua sendo a fonte unica da interface, dos atalhos e das regras de venda.
